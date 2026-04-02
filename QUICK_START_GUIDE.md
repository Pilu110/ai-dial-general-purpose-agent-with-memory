# 🚀 QUICK START GUIDE - Running the Long-Term Memory System

## Prerequisites

✅ Already Installed:
- Python 3.11+ (with venv activated)
- Docker & Docker Compose
- VPN connection to ai-proxy.lab.epam.com

## Step 1: Run Smoke Tests (Local - No Docker Needed)

```bash
cd C:\Users\IstvanVincze\PycharmProjects\ai-dial-general-purpose-agent-with-memory
python test_memory_smoke_tests.py
```

**Expected Output:**
```
✅ TEST: Memory Models
✅ TEST: Memory Store Initialization
✅ TEST: Embedding Generation
✅ TEST: Deduplication Check Logic
✅ TEST: Deduplication Algorithm
✅ TEST: Memory Tools Names and Descriptions
✅ TEST: Memory Tools Parameters
✅ TEST: Memory Tools Schemas

RESULTS: 8 passed, 0 failed out of 8 tests
```

**Status:** ✅ Tests are PASSING

---

## Step 2: Set Environment Variables

### On Windows PowerShell:
```powershell
$env:DIAL_API_KEY = "your-api-key-here"
$env:DIAL_ENDPOINT = "http://localhost:8080"
```

### Or create `.env` file in project root:
```
DIAL_API_KEY=your-api-key-here
DIAL_ENDPOINT=http://localhost:8080
DEPLOYMENT_NAME=gpt-4o
```

---

## Step 3: Start Docker Services (with VPN enabled)

```bash
# Navigate to project directory
cd C:\Users\IstvanVincze\PycharmProjects\ai-dial-general-purpose-agent-with-memory

# Start all services
docker-compose up -d

# Verify services are running
docker-compose ps
```

**Expected Services Running:**
```
NAME                              STATUS
ai-dial-general-purpose-agent-with-memory_chat_1                Up
ai-dial-general-purpose-agent-with-memory_core_1                Up
ai-dial-general-purpose-agent-with-memory_redis_1               Up
ai-dial-general-purpose-agent-with-memory_adapter-dial_1        Up
ai-dial-general-purpose-agent-with-memory_themes_1              Up
ai-dial-general-purpose-agent-with-memory_python-interpreter_1  Up
ai-dial-general-purpose-agent-with-memory_ddg-search_1          Up
```

**Wait 10-15 seconds for services to fully initialize.**

---

## Step 4: Access the Chat UI

Open your browser and navigate to:
```
http://localhost:3000
```

**Login Credentials:**
```
API Key: dial_api_key
```

---

## Step 5: Test Memory Features

### Test 1: Store Memories

**User Message:**
```
Remember these facts about me:
1. My name is John
2. I live in Paris, France
3. I work as a Python developer
4. I like machine learning and AI
5. I want to learn Rust
```

**Expected Behavior:**
- LLM reads your facts
- System prompt triggers `store_memory` tool
- Each fact stored with:
  - Category: personal_info / preferences / goals
  - Importance: 0.7-0.9 (high importance)
  - Topics: relevant tags

**Chat shows:**
```
✅ Memory stored successfully: My name is John
✅ Memory stored successfully: I live in Paris, France
✅ Memory stored successfully: I work as a Python developer
[... etc ...]
```

### Test 2: Search Memories (Contextual Question)

**User Message (in NEW conversation):**
```
What should I wear today?
```

**Expected Behavior:**
1. LLM receives message
2. System prompt triggers `search_memory` tool
3. LLM queries: "location where user lives"
4. Tool returns: "I live in Paris, France"
5. LLM uses context in response:
   ```
   Since you're in Paris, I'd recommend...
   [Weather-based recommendation for Paris]
   ```

### Test 3: Search with Specific Query

**User Message:**
```
What programming language should I learn next?
```

**Expected Behavior:**
1. System prompt triggers `search_memory`
2. LLM queries: "programming languages user knows or learning"
3. Tool returns: 
   - "I work as a Python developer"
   - "I want to learn Rust"
4. LLM provides personalized recommendation:
   ```
   Since you already know Python and want to learn Rust,
   I'd recommend focusing on Rust's ownership model because...
   ```

### Test 4: Multiple Searches in One Message

**User Message:**
```
Suggest a tech conference for me in a city I like
```

**Expected Behavior:**
1. LLM searches memory with query: "location city preference"
2. Gets: "I live in Paris"
3. LLM searches memory with query: "technology interests programming"
4. Gets: "Python developer", "machine learning", "AI"
5. LLM responds:
   ```
   Based on your interests in ML/AI and location in Paris,
   I'd recommend Paris Machine Learning Conference 2026...
   ```

### Test 5: Delete All Memories

**User Message:**
```
Clear all my memories
```

**Expected Behavior:**
- LLM triggers `delete_memory` tool
- Tool deletes file from DIAL bucket
- Cache cleared
- Response confirms: "All memories have been successfully deleted"

**Verify Deletion:**

**Next User Message:**
```
What do you know about me?
```

**Expected Response:**
```
I don't have any information about you in my memory.
You haven't shared any personal details yet.
```

---

## Step 6: Verify Persistence

**Conversation 1:**
```
Remember: I am 25 years old and I work in Berlin
```
✅ Memory stored

**Conversation 2 (NEW):**
```
Where do I work?
```

**Expected Response:**
```
Based on the information I remember about you,
you work in Berlin.
```

✅ Memory persists across conversations!

---

## Monitoring & Debugging

### Check Memory File in DIAL

Memory files are stored at:
```
files/{user_home}/__long-memories/data.json
```

Accessible through Chat UI → Attachments manager

### View Service Logs

```bash
# View all logs
docker-compose logs -f

# View specific service
docker-compose logs -f core
docker-compose logs -f adapter-dial
```

### Test Memory File Structure

The stored memory file contains JSON like:
```json
{
  "memories": [
    {
      "data": {
        "id": 1234567890,
        "content": "I live in Paris",
        "importance": 0.9,
        "category": "personal_info",
        "topics": ["location", "residence"]
      },
      "embedding": [0.123, 0.456, ...]
    }
  ],
  "updated_at": "2026-03-30T10:30:00Z",
  "last_deduplicated_at": null
}
```

---

## Troubleshooting

### Issue: "Connection refused" to http://localhost:8080
**Solution:** 
- Verify Docker services are running: `docker-compose ps`
- Wait 15 seconds for services to initialize
- Check logs: `docker-compose logs core`

### Issue: Memory not storing
**Solution:**
- Verify DIAL_API_KEY is set correctly
- Check Chat UI shows tool execution in stage
- Check browser console for errors (F12)

### Issue: "No memories found" when searching
**Solution:**
- Store memories first with Test 1
- Ensure you're using `store_memory` tool (should show in chat stages)
- Wait for response to complete before next message

### Issue: Docker won't start
**Solution:**
```bash
# Stop all containers
docker-compose down

# Remove volumes
docker volume prune

# Start fresh
docker-compose up -d
```

---

## Advanced Testing

### Test Deduplication

Store similar memories:
```
Remember:
1. I like Python programming
2. I prefer Python language
3. I work with Python code
```

Wait 24+ hours and search → Should show deduplicated results
(Or check memory file - duplicates removed, highest importance kept)

### Test Embedding Quality

Store varied memories:
```
Remember:
- I like coffee
- I prefer Python
- I enjoy coding
```

Search with:
```
What programming languages do you like?
```

Should retrieve Python-related memory, not coffee!

---

## Quick Command Reference

```bash
# Run smoke tests
python test_memory_smoke_tests.py

# Start services
docker-compose up -d

# Stop services
docker-compose down

# View logs
docker-compose logs -f

# Restart a service
docker-compose restart core

# View running services
docker-compose ps

# Access Chat UI
http://localhost:3000
```

---

## Expected Timeline

| Step | Duration | Status |
|------|----------|--------|
| Smoke tests | 5-10 sec | ✅ Local |
| Docker startup | 10-15 sec | ⏳ First time |
| Chat UI load | 2-3 sec | ✅ Browser |
| Memory store | 1-2 sec | ✅ Per message |
| Memory search | 1-2 sec | ✅ Per message |
| Deduplication | 1-3 sec | ✅ >10 memories |

---

## Success Indicators

✅ You'll know it's working when:

1. **Smoke tests pass** - All 8/8 tests pass locally
2. **Services run** - `docker-compose ps` shows 7+ running
3. **Chat loads** - http://localhost:3000 shows chat interface
4. **Memory stores** - Chat shows "✅ Memory stored successfully"
5. **Memory searches** - LLM uses stored context in responses
6. **Persistence works** - New conversation retrieves old memories
7. **Dedup works** - Similar memories are consolidated

---

## What's Happening Behind the Scenes

### When You Store Memory:
1. You type fact → LLM reads system prompt
2. LLM recognizes important info
3. LLM calls `store_memory` tool with JSON args
4. Tool encodes text to 384-dim vector (all-MiniLM-L6-v2)
5. Memory saved to DIAL bucket + local cache
6. Confirmation shown in chat

### When You Search Memory:
1. You ask contextual question → LLM reads system prompt
2. LLM calls `search_memory` tool
3. Tool encodes your question to vector
4. FAISS finds similar memories (cosine similarity)
5. Tool returns top memories to LLM
6. LLM uses context in response

### Deduplication:
1. Triggered when search_memories() is called
2. If >10 memories AND (no dedup history OR >24 hours)
3. FAISS k-NN search finds similar vectors
4. Duplicates (similarity >0.75) removed, keeping high importance
5. Result saved back to DIAL

---

**Status: ✅ READY TO USE**

Follow these steps to test the memory system!

