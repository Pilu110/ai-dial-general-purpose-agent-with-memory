import os
os.environ['OMP_NUM_THREADS'] = '1'

import json
from datetime import datetime, UTC, timedelta
import numpy as np
import faiss
from aidial_client import AsyncDial
from sentence_transformers import SentenceTransformer

from task.tools.memory._models import Memory, MemoryData, MemoryCollection


class LongTermMemoryStore:
    """
    Manages long-term memory storage for users.

    Storage format: Single JSON file per user in DIAL bucket
    - File: {user_id}/long-memories.json
    - Caching: In-memory cache with conversation_id as key
    - Deduplication: O(n log n) using FAISS batch search
    """

    DEDUP_INTERVAL_HOURS = 24

    def __init__(self, endpoint: str):
        #TODO:
        # 1. Set endpoint
        # 2. Create SentenceTransformer as model, model name is `all-MiniLM-L6-v2`
        # 3. Create cache, doct of str and MemoryCollection (it is imitation of cache, normally such cache should be set aside)
        # 4. Make `faiss.omp_set_num_threads(1)` (without this set up you won't be able to work in debug mode in `_deduplicate_fast` method
        self.endpoint = endpoint
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.cache: dict[str, MemoryCollection] = {}
        faiss.omp_set_num_threads(1)

    async def _get_memory_file_path(self, dial_client: AsyncDial) -> str:
        """Get the path to the memory file in DIAL bucket."""
        #TODO:
        # 1. Get DIAL app home path
        # 2. Return string with path in such format: `files/{bucket_with_app_home}/__long-memories/data.json`
        #    The memories will persist in appdata for this agent in `__long-memories` folder and `data.json` file
        #    (You will be able to check it also in Chat UI in attachments)
        files_home = await dial_client.my_files_home()
        return f"{files_home}/__long-memories/data.json"

    async def _load_memories(self, api_key: str) -> MemoryCollection:
        #TODO:
        # 1. Create AsyncDial client (api_version is 2025-01-01-preview)
        # 2. Get memory file path
        # 3. Check cache: cache is dict of str and MemoryCollection, for the key we will use `memory file path` to make
        #    it simple. Such key will be unique for user and will allow to access memories across different
        #    conversations and only user can access them. In case if cache is present return its MemoryCollection.
        # ---
        # Below is logic when cache is not present:
        # 4. Open try-except block:
        #   - in try:
        #       - download file content
        #       - in response get content and decode it with 'utf-8'
        #       - load content with `json`
        #       - create MemoryCollection (it is pydentic model, use `model_validate` method)
        #   - in except:
        #       - create MemoryCollection (it will have empty memories, set up time for updated_at, more detailed take
        #         a look at MemoryCollection pydentic model and it Fields)
        # 5. Return created MemoryCollection
        dial_client = AsyncDial(
            base_url=self.endpoint,
            api_key=api_key,
            api_version='2025-01-01-preview'
        )
        
        memory_file_path = await self._get_memory_file_path(dial_client)
        
        # Check cache first
        if memory_file_path in self.cache:
            return self.cache[memory_file_path]
        
        # Try to load from DIAL bucket
        try:
            response = await dial_client.files.download(memory_file_path)
            content = response.content.decode('utf-8')
            collection_data = json.loads(content)
            collection = MemoryCollection.model_validate(collection_data)
        except Exception:
            # If file doesn't exist, create empty collection
            collection = MemoryCollection()

        self.cache[memory_file_path] = collection
        
        return collection

    async def _save_memories(self, api_key: str, memories: MemoryCollection):
        """Save memories to DIAL bucket and update cache."""
        dc = AsyncDial(base_url=self.endpoint, api_key=api_key, api_version='2025-01-01-preview')
        fp = await self._get_memory_file_path(dc)
        memories.updated_at = datetime.now(UTC)
        await dc.files.upload(url=fp, file=memories.model_dump_json(exclude_none=True).encode('utf-8'))
        self.cache[fp] = memories

    async def add_memory(self, api_key: str, content: str, importance: float, category: str, topics: list[str]) -> str:
        """Add a new memory to storage."""
        m = await self._load_memories(api_key)
        emb = self.model.encode([content])[0].tolist()
        mem = Memory(data=MemoryData(id=int(datetime.now(UTC).timestamp()), content=content, importance=importance, category=category, topics=topics), embedding=emb)
        m.memories.append(mem)
        await self._save_memories(api_key, m)
        return f"Memory stored successfully: {content}"

    async def search_memories(self, api_key: str, query: str, top_k: int = 5) -> list[MemoryData]:
        """Search memories using semantic similarity. Returns list of MemoryData objects (without embeddings)."""
        c = await self._load_memories(api_key)
        if not c.memories: return []
        if self._needs_deduplication(c):
            c = await self._deduplicate_and_save(api_key, c)
        ve = np.array([m.embedding for m in c.memories], dtype=np.float32)
        faiss.normalize_L2(ve)
        qe = self.model.encode([query]).astype(np.float32)
        faiss.normalize_L2(qe)
        idx = faiss.IndexFlatIP(ve.shape[1])
        idx.add(ve)
        k = min(max(1, top_k), len(c.memories))
        _, ixes = idx.search(qe, k)
        return [c.memories[i].data for i in ixes[0] if i >= 0]

    async def get_all_memories(self, api_key: str) -> list[MemoryData]:
        """Return all user memories as MemoryData entries."""
        collection = await self._load_memories(api_key)
        return [memory.data for memory in collection.memories]

    async def replace_memories(self, api_key: str, memories: list[dict]) -> str:
        """Replace all memories with the provided normalized memory entries."""
        collection = MemoryCollection()
        for idx, item in enumerate(memories):
            content = str(item.get("content", "")).strip()
            if not content:
                continue

            importance = float(item.get("importance", 0.5))
            importance = max(0.0, min(1.0, importance))
            category = str(item.get("category", "general")).strip() or "general"
            topics = item.get("topics", [])
            topics = [str(topic).strip() for topic in topics if str(topic).strip()]

            embedding = self.model.encode([content])[0].tolist()
            memory = Memory(
                data=MemoryData(
                    id=int(datetime.now(UTC).timestamp()) + idx,
                    content=content,
                    importance=importance,
                    category=category,
                    topics=topics,
                ),
                embedding=embedding,
            )
            collection.memories.append(memory)

        await self._save_memories(api_key, collection)
        return f"Memory profile updated with {len(collection.memories)} entries."

    def _needs_deduplication(self, collection: MemoryCollection) -> bool:
        """Check if deduplication is needed (>24 hours since last deduplication)."""
        if len(collection.memories) <= 10: return False
        if collection.last_deduplicated_at is None: return True
        return (datetime.now(UTC) - collection.last_deduplicated_at) > timedelta(hours=self.DEDUP_INTERVAL_HOURS)

    async def _deduplicate_and_save(self, api_key: str, collection: MemoryCollection) -> MemoryCollection:
        """Deduplicate memories synchronously and save the result. Returns the updated collection."""
        collection.memories = self._deduplicate_fast(collection.memories)
        collection.last_deduplicated_at = datetime.now(UTC)
        await self._save_memories(api_key, collection)
        return collection

    def _deduplicate_fast(self, memories: list[Memory]) -> list[Memory]:
        """Fast deduplication using FAISS batch search with cosine similarity (threshold 0.75, keep higher importance)."""
        if len(memories) <= 1:
            return memories
        vectors = np.array([m.embedding for m in memories], dtype=np.float32)
        faiss.normalize_L2(vectors)
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        k = min(10, len(memories))
        scores, neighbors = index.search(vectors, k)
        keep = np.ones(len(memories), dtype=bool)
        threshold = 0.75
        for i in range(len(memories)):
            if not keep[i]:
                continue
            for rank in range(1, k):
                j = int(neighbors[i][rank])
                if j < 0 or not keep[j]:
                    continue
                if float(scores[i][rank]) < threshold:
                    continue
                left = memories[i].data
                right = memories[j].data
                if right.importance > left.importance:
                    keep[i] = False
                    break
                if right.importance < left.importance:
                    keep[j] = False
                    continue
                if right.id > left.id:
                    keep[j] = False
                else:
                    keep[i] = False
                    break
        return [m for idx, m in enumerate(memories) if keep[idx]]

    async def delete_all_memories(self, api_key: str, ) -> str:
        """
        Delete all memories for the user.

        Removes the memory file from DIAL bucket and clears the cache
        for the current conversation.
        """
        #TODO:
        # 1. Create AsyncDial client
        # 2. Get memory file path
        # 3. Delete file
        # 4. Return info about successful memory deletion
        dial_client = AsyncDial(
            base_url=self.endpoint,
            api_key=api_key,
            api_version='2025-01-01-preview'
        )
        
        memory_file_path = await self._get_memory_file_path(dial_client)
        
        try:
            await dial_client.files.delete(memory_file_path)
            # Clear from cache as well
            if memory_file_path in self.cache:
                del self.cache[memory_file_path]
            return "All memories have been successfully deleted."
        except Exception as e:
            return f"Memories deleted (or did not exist): {str(e)}"
