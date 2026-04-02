import asyncio
import json
import os
from typing import Any

from aidial_client import AsyncDial
from aidial_client.types.chat.legacy.chat_completion import CustomContent, ToolCall
from aidial_sdk.chat_completion import Message, Role, Choice, Request, Response

from task.tools.base import BaseTool
from task.tools.memory.memory_store import LongTermMemoryStore
from task.tools.memory._models import MemoryData
from task.tools.models import ToolCallParams
from task.utils.constants import TOOL_CALL_HISTORY_KEY
from task.utils.history import unpack_messages
from task.utils.stage import StageProcessor


class GeneralPurposeAgent:

    def __init__(
            self,
            endpoint: str,
            system_prompt: str,
            tools: list[BaseTool],
            memory_store: LongTermMemoryStore,
            fast_deployment_name: str,
    ):
        self.endpoint = endpoint
        self.system_prompt = system_prompt
        self.tools = tools
        self.memory_store = memory_store
        self.fast_deployment_name = fast_deployment_name
        self._tools_dict: dict[str, BaseTool] = {
            tool.name: tool
            for tool in tools
        }
        self.state = {
            TOOL_CALL_HISTORY_KEY: []
        }

    async def handle_request(
            self, deployment_name: str, choice: Choice, request: Request, response: Response) -> Message:
        api_key = request.api_key
        internal_api_key = os.getenv('DIAL_API_KEY') or api_key

        client: AsyncDial = AsyncDial(
            base_url=self.endpoint,
            api_key=internal_api_key,
            api_version='2025-01-01-preview'
        )

        user_memories = await self.memory_store.get_all_memories(internal_api_key)

        chunks = await client.chat.completions.create(
            messages=self._prepare_messages(request.messages, user_memories),
            tools=[tool.schema for tool in self.tools],
            stream=True,
            deployment_name=deployment_name,
        )

        tool_call_index_map = {}
        content = ''
        custom_content: CustomContent = CustomContent(attachments=[])
        async for chunk in chunks:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    choice.append_content(delta.content)
                    content += delta.content

                if delta.tool_calls:
                    for tool_call_delta in delta.tool_calls:
                        if tool_call_delta.id:
                            tool_call_index_map[tool_call_delta.index] = tool_call_delta
                        else:
                            tool_call = tool_call_index_map[tool_call_delta.index]
                            if tool_call_delta.function:
                                argument_chunk = tool_call_delta.function.arguments or ''
                                tool_call.function.arguments += argument_chunk

        assistant_message = Message(
            role=Role.ASSISTANT,
            content=content,
            custom_content=custom_content,
            tool_calls=[ToolCall.validate(tool_call) for tool_call in tool_call_index_map.values()]
        )

        if assistant_message.tool_calls:
            tasks = [
                self._process_tool_call(
                    tool_call=tool_call,
                    choice=choice,
                    api_key=internal_api_key,
                    conversation_id=request.headers['x-conversation-id']
                )
                for tool_call in assistant_message.tool_calls
            ]
            tool_messages = await asyncio.gather(*tasks)

            self.state[TOOL_CALL_HISTORY_KEY].append(assistant_message.dict(exclude_none=True))
            self.state[TOOL_CALL_HISTORY_KEY].extend(tool_messages)

            return await self.handle_request(
                deployment_name=deployment_name,
                choice=choice,
                request=request,
                response=response
            )

        latest_user_message = self._latest_user_message(request.messages)
        if latest_user_message and await self._has_new_user_info(
                client=client,
                user_message=latest_user_message,
                assistant_message=content):
            await self._update_user_info_profile(
                client=client,
                api_key=internal_api_key,
                existing_memories=user_memories,
                user_message=latest_user_message,
                assistant_message=content,
            )

        choice.set_state(self.state)

        return assistant_message

    def _prepare_messages(self, messages: list[Message], user_memories: list[MemoryData]) -> list[dict[str, Any]]:
        unpacked_messages = unpack_messages(messages, self.state[TOOL_CALL_HISTORY_KEY])
        memory_context = self._build_user_memory_context(user_memories)
        unpacked_messages.insert(
            0,
            {
                "role": Role.SYSTEM.value,
                "content": f"{self.system_prompt}\n\n## User profile context\n{memory_context}",
            }
        )

        print("\nHistory:")
        for msg in unpacked_messages:
            print(f"     {json.dumps(msg)}")

        print(f"{'-' * 100}\n")

        return unpacked_messages

    def _build_user_memory_context(self, memories: list[MemoryData]) -> str:
        if not memories:
            return "No stored user information yet."

        lines = []
        for memory in sorted(memories, key=lambda item: item.importance, reverse=True):
            topics = ", ".join(memory.topics) if memory.topics else "none"
            lines.append(
                f"- [{memory.category}] importance={memory.importance:.2f}; topics={topics}; content={memory.content}"
            )
        return "\n".join(lines)

    def _latest_user_message(self, messages: list[Message]) -> str:
        for message in reversed(messages):
            role_value = message.role.value if hasattr(message.role, "value") else str(message.role).lower()
            if role_value == Role.USER.value:
                return self._message_text(message.content)
        return ""

    def _message_text(self, content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    chunks.append(str(item.get("text", "")))
                else:
                    chunks.append(str(item))
            return "\n".join([chunk for chunk in chunks if chunk.strip()])
        return str(content)

    async def _has_new_user_info(self, client: AsyncDial, user_message: str, assistant_message: str) -> bool:
        detection_prompt = (
            "You detect if NEW durable user information exists in conversation snippets. "
            "Durable user information includes: personal profile, preferences, long-term goals, ongoing projects, "
            "stable context. Answer with only true or false."
        )
        check_messages = [
            {"role": Role.SYSTEM.value, "content": detection_prompt},
            {
                "role": Role.USER.value,
                "content": (
                    f"Latest user message:\n{user_message}\n\n"
                    f"Latest assistant message:\n{assistant_message}\n\n"
                    "Is there new durable user information not previously known?"
                )
            }
        ]

        try:
            completion = await client.chat.completions.create(
                messages=check_messages,
                stream=False,
                deployment_name=self.fast_deployment_name,
            )
            raw = completion.choices[0].message.content if completion.choices else "false"
            decision = str(raw).strip().lower()
            return decision.startswith("true")
        except Exception as exc:
            print(f"User info detection failed, skipping profile update: {exc}")
            return False

    async def _update_user_info_profile(
            self,
            client: AsyncDial,
            api_key: str,
            existing_memories: list[MemoryData],
            user_message: str,
            assistant_message: str,
    ) -> None:
        existing_payload = [
            {
                "content": memory.content,
                "category": memory.category,
                "importance": memory.importance,
                "topics": memory.topics,
            }
            for memory in existing_memories
        ]

        update_prompt = (
            "You update stored durable user information. "
            "Given existing user info and latest conversation messages, output the FULL updated memory profile as JSON array. "
            "Each item must contain content, category, importance, topics. "
            "Keep only durable user facts, drop transient details. Return only JSON."
        )
        update_messages = [
            {"role": Role.SYSTEM.value, "content": update_prompt},
            {
                "role": Role.USER.value,
                "content": json.dumps(
                    {
                        "existing_user_info": existing_payload,
                        "latest_user_message": user_message,
                        "latest_assistant_message": assistant_message,
                    },
                    ensure_ascii=True,
                )
            }
        ]

        try:
            completion = await client.chat.completions.create(
                messages=update_messages,
                stream=False,
                deployment_name=self.fast_deployment_name,
            )
            raw = completion.choices[0].message.content if completion.choices else "[]"
            raw_text = str(raw).strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.strip("`")
                raw_text = raw_text.replace("json", "", 1).strip()
            profile = json.loads(raw_text)
            if isinstance(profile, list):
                await self.memory_store.replace_memories(api_key=api_key, memories=profile)
        except Exception as exc:
            print(f"User info update chain failed, profile unchanged: {exc}")

    async def _process_tool_call(self, tool_call: ToolCall, choice: Choice, api_key: str, conversation_id: str) -> dict[
        str, Any]:
        tool_name = tool_call.function.name
        stage = StageProcessor.open_stage(
            choice,
            tool_name
        )

        tool = self._tools_dict[tool_name]

        if tool.show_in_stage:
            stage.append_content("## Request arguments: \n")
            stage.append_content(
                f"```json\n\r{json.dumps(json.loads(tool_call.function.arguments), indent=2)}\n\r```\n\r")
            stage.append_content("## Response: \n")

        tool_message = await tool.execute(
            ToolCallParams(
                tool_call=tool_call,
                stage=stage,
                choice=choice,
                api_key=api_key,
                conversation_id=conversation_id
            )
        )

        StageProcessor.close_stage_safely(stage)

        return tool_message.dict(exclude_none=True)
