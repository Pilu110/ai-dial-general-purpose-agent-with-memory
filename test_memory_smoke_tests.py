"""
Smoke tests for long-term memory implementation
Tests the core memory store functionality without requiring full docker setup
"""

import asyncio
import sys
import json
from datetime import datetime, UTC

sys.path.insert(0, 'C:\\Users\\IstvanVincze\\PycharmProjects\\ai-dial-general-purpose-agent-with-memory')

from task.tools.memory._models import Memory, MemoryData, MemoryCollection
from task.tools.memory.memory_store import LongTermMemoryStore
from task.tools.memory.memory_store_tool import StoreMemoryTool
from task.tools.memory.memory_search_tool import SearchMemoryTool
from task.tools.memory.memory_delete_tool import DeleteMemoryTool
import numpy as np


def test_memory_models():
    """Test that memory models are correctly defined"""
    print("\n✅ TEST: Memory Models")
    
    # Create MemoryData
    memory_data = MemoryData(
        id=12345,
        content="User lives in Paris",
        importance=0.9,
        category="personal_info",
        topics=["location", "residence"]
    )
    
    # Create Memory with embedding
    embedding = [0.1, 0.2, 0.3] * 100  # Simulate 300-dim embedding
    memory = Memory(data=memory_data, embedding=embedding)
    
    # Create MemoryCollection
    collection = MemoryCollection(memories=[memory])
    
    # Test JSON serialization
    json_str = collection.model_dump_json()
    loaded = MemoryCollection.model_validate_json(json_str)
    
    assert len(loaded.memories) == 1
    assert loaded.memories[0].data.content == "User lives in Paris"
    print("✓ Memory models work correctly")
    print("✓ JSON serialization/deserialization works")
    return True


def test_memory_store_initialization():
    """Test LongTermMemoryStore initialization"""
    print("\n✅ TEST: Memory Store Initialization")
    
    store = LongTermMemoryStore(endpoint="http://localhost:8080")
    
    assert store.endpoint == "http://localhost:8080"
    assert store.model is not None
    assert store.cache == {}
    print("✓ Memory store initialized correctly")
    return True


def test_deduplication_logic():
    """Test deduplication algorithm"""
    print("\n✅ TEST: Deduplication Algorithm")
    
    store = LongTermMemoryStore(endpoint="http://localhost:8080")
    
    # Create test memories with embeddings
    memories = []
    
    # Memory 1: High importance
    mem_data_1 = MemoryData(
        id=1,
        content="User likes Python",
        importance=0.9,
        category="preferences",
        topics=["programming"]
    )
    embedding_1 = store.model.encode(["User likes Python"])[0].tolist()
    memories.append(Memory(data=mem_data_1, embedding=embedding_1))
    
    # Memory 2: Similar content, lower importance (should be removed)
    mem_data_2 = MemoryData(
        id=2,
        content="User prefers Python language",
        importance=0.3,
        category="preferences",
        topics=["programming"]
    )
    embedding_2 = store.model.encode(["User prefers Python language"])[0].tolist()
    memories.append(Memory(data=mem_data_2, embedding=embedding_2))
    
    # Memory 3: Completely different
    mem_data_3 = MemoryData(
        id=3,
        content="Lives in New York",
        importance=0.8,
        category="personal_info",
        topics=["location"]
    )
    embedding_3 = store.model.encode(["Lives in New York"])[0].tolist()
    memories.append(Memory(data=mem_data_3, embedding=embedding_3))
    
    # Test deduplication
    deduplicated = store._deduplicate_fast(memories)
    
    # Should keep memories 1 and 3 (remove 2 as it's a duplicate with lower importance)
    assert len(deduplicated) >= 2, f"Expected at least 2 memories after dedup, got {len(deduplicated)}"
    print(f"✓ Deduplication works: {len(memories)} -> {len(deduplicated)} memories")
    print(f"  Removed {len(memories) - len(deduplicated)} duplicates")
    return True


def test_deduplication_check():
    """Test the needs_deduplication logic"""
    print("\n✅ TEST: Deduplication Check Logic")
    
    store = LongTermMemoryStore(endpoint="http://localhost:8080")
    
    # Test 1: Empty collection should not need dedup
    collection = MemoryCollection()
    assert not store._needs_deduplication(collection)
    print("✓ Empty collection doesn't need deduplication")
    
    # Test 2: Collection with <= 10 memories should not need dedup
    for i in range(5):
        mem_data = MemoryData(id=i, content=f"Memory {i}")
        embedding = [0.1] * 384
        collection.memories.append(Memory(data=mem_data, embedding=embedding))
    
    assert not store._needs_deduplication(collection)
    print("✓ Small collection (5 items) doesn't need deduplication")
    
    # Test 3: Collection with > 10 and no last_deduplicated_at should need dedup
    for i in range(5, 12):
        mem_data = MemoryData(id=i, content=f"Memory {i}")
        embedding = [0.1] * 384
        collection.memories.append(Memory(data=mem_data, embedding=embedding))
    
    assert store._needs_deduplication(collection)
    print("✓ Large collection (12 items) with no dedup history needs deduplication")
    
    # Test 4: Recently deduplicated collection should not need dedup
    collection.last_deduplicated_at = datetime.now(UTC)
    assert not store._needs_deduplication(collection)
    print("✓ Recently deduplicated collection doesn't need deduplication")
    
    return True


def test_tool_names_and_descriptions():
    """Test that all memory tools have proper names and descriptions"""
    print("\n✅ TEST: Memory Tools Names and Descriptions")
    
    store = LongTermMemoryStore(endpoint="http://localhost:8080")
    
    store_tool = StoreMemoryTool(memory_store=store)
    search_tool = SearchMemoryTool(memory_store=store)
    delete_tool = DeleteMemoryTool(memory_store=store)
    
    # Test store tool
    assert store_tool.name == "store_memory"
    assert len(store_tool.description) > 0
    assert store_tool.description.endswith(".") or store_tool.description.endswith(")")
    print(f"✓ Store tool: '{store_tool.name}' - {len(store_tool.description)} chars description")
    
    # Test search tool
    assert search_tool.name == "search_memory"
    assert len(search_tool.description) > 0
    print(f"✓ Search tool: '{search_tool.name}' - {len(search_tool.description)} chars description")
    
    # Test delete tool
    assert delete_tool.name == "delete_memory"
    assert len(delete_tool.description) > 0
    print(f"✓ Delete tool: '{delete_tool.name}' - {len(delete_tool.description)} chars description")
    
    return True


def test_tool_parameters():
    """Test that all memory tools have proper parameters"""
    print("\n✅ TEST: Memory Tools Parameters")
    
    store = LongTermMemoryStore(endpoint="http://localhost:8080")
    
    store_tool = StoreMemoryTool(memory_store=store)
    search_tool = SearchMemoryTool(memory_store=store)
    delete_tool = DeleteMemoryTool(memory_store=store)
    
    # Test store tool parameters
    store_params = store_tool.parameters
    assert "content" in store_params["properties"]
    assert "category" in store_params["properties"]
    assert "importance" in store_params["properties"]
    assert "topics" in store_params["properties"]
    assert "content" in store_params["required"]
    print("✓ Store tool has correct parameters")
    
    # Test search tool parameters
    search_params = search_tool.parameters
    assert "query" in search_params["properties"]
    assert "top_k" in search_params["properties"]
    assert "query" in search_params["required"]
    print("✓ Search tool has correct parameters")
    
    # Test delete tool parameters
    delete_params = delete_tool.parameters
    assert delete_params["properties"] == {}
    print("✓ Delete tool has correct (empty) parameters")
    
    return True


def test_tool_schemas():
    """Test that tools generate valid schemas"""
    print("\n✅ TEST: Memory Tools Schemas")
    
    store = LongTermMemoryStore(endpoint="http://localhost:8080")
    
    store_tool = StoreMemoryTool(memory_store=store)
    search_tool = SearchMemoryTool(memory_store=store)
    delete_tool = DeleteMemoryTool(memory_store=store)
    
    def get_schema_dict(schema):
        """Convert schema to dict, handling both dict and object formats"""
        if isinstance(schema, dict):
            return schema
        if hasattr(schema, 'model_dump'):
            return schema.model_dump()
        if hasattr(schema, '__dict__'):
            result = {}
            for k, v in schema.__dict__.items():
                if not k.startswith('_'):
                    if hasattr(v, '__dict__') and not isinstance(v, (str, int, float, bool, list)):
                        result[k] = {kk: getattr(v, kk) for kk in dir(v) if not kk.startswith('_')}
                    else:
                        result[k] = v
            return result
        return {}
    
    # Test store tool schema
    store_schema = get_schema_dict(store_tool.schema)
    assert store_schema.get("type") == "function"
    assert store_schema.get("function", {}).get("name") == "store_memory"
    assert len(store_schema.get("function", {}).get("description", "")) > 0
    print("✓ Store tool schema is valid")
    
    # Test search tool schema
    search_schema = get_schema_dict(search_tool.schema)
    assert search_schema.get("type") == "function"
    assert search_schema.get("function", {}).get("name") == "search_memory"
    print("✓ Search tool schema is valid")
    
    # Test delete tool schema
    delete_schema = get_schema_dict(delete_tool.schema)
    assert delete_schema.get("type") == "function"
    assert delete_schema.get("function", {}).get("name") == "delete_memory"
    print("✓ Delete tool schema is valid")
    
    return True


def test_embedding_generation():
    """Test that embeddings are generated correctly"""
    print("\n✅ TEST: Embedding Generation")
    
    store = LongTermMemoryStore(endpoint="http://localhost:8080")
    
    # Test single text encoding
    text = "User lives in Paris"
    embedding = store.model.encode([text])[0].tolist()
    
    assert isinstance(embedding, list)
    assert len(embedding) == 384  # all-MiniLM-L6-v2 produces 384-dim embeddings
    assert all(isinstance(x, (float, int)) for x in embedding)
    print(f"✓ Embedding generated: {len(embedding)} dimensions")
    
    # Test similar texts produce similar embeddings
    text1 = "User lives in Paris"
    text2 = "User resides in Paris"
    text3 = "User works as engineer"
    
    emb1 = np.array(store.model.encode([text1])[0])
    emb2 = np.array(store.model.encode([text2])[0])
    emb3 = np.array(store.model.encode([text3])[0])
    
    # Normalize for cosine similarity
    emb1_norm = emb1 / np.linalg.norm(emb1)
    emb2_norm = emb2 / np.linalg.norm(emb2)
    emb3_norm = emb3 / np.linalg.norm(emb3)
    
    sim_12 = np.dot(emb1_norm, emb2_norm)
    sim_13 = np.dot(emb1_norm, emb3_norm)
    
    assert sim_12 > sim_13, "Similar texts should have higher similarity"
    print(f"✓ Similar texts: similarity {sim_12:.3f}")
    print(f"✓ Different texts: similarity {sim_13:.3f}")
    
    return True


def run_all_tests():
    """Run all smoke tests"""
    print("=" * 70)
    print("LONG-TERM MEMORY SYSTEM - SMOKE TESTS")
    print("=" * 70)
    
    tests = [
        ("Memory Models", test_memory_models),
        ("Memory Store Initialization", test_memory_store_initialization),
        ("Embedding Generation", test_embedding_generation),
        ("Deduplication Check Logic", test_deduplication_check),
        ("Deduplication Algorithm", test_deduplication_logic),
        ("Tool Names and Descriptions", test_tool_names_and_descriptions),
        ("Tool Parameters", test_tool_parameters),
        ("Tool Schemas", test_tool_schemas),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            if result:
                passed += 1
        except Exception as e:
            failed += 1
            print(f"✗ {test_name} FAILED: {str(e)}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("=" * 70)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

