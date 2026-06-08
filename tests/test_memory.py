import asyncio
import pytest
from pathlib import Path
from jarvis.memory.memory_manager import MemoryManager

@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test_jarvis.db"

@pytest.mark.asyncio
async def test_memory_manager_basic_operations(db_path):
    memory = MemoryManager(db_path)
    await memory.init_db()
    
    # 1. Test session creation
    session_id = "test_session_1"
    await memory.create_session(session_id, "test-model", "test-instructions")
    
    # 2. Test message insertion
    msg_id = await memory.add_message(session_id, "user", "Hello Jarvis, let's build a workstation tool.")
    assert msg_id > 0
    
    await memory.add_message(session_id, "assistant", "Sure Shaun. What capability do we need first?")
    
    # 3. Test history retrieval
    history = await memory.get_session_history(session_id)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert "workstation" in history[0]["content"]
    assert history[1]["role"] == "assistant"
    
    # 4. Test facts storage and retrieval
    await memory.upsert_fact("system", "os_version", "Linux Mint 21")
    await memory.upsert_fact("system", "hardware", "HP ZBook")
    
    facts = await memory.get_facts("system")
    assert len(facts) == 2
    assert facts[0]["subject"] == "hardware"
    assert facts[0]["value"] == "HP ZBook"
    
    # 5. Test preferences
    await memory.upsert_preference("editor", "VS Code")
    prefs = await memory.get_preferences()
    assert prefs["editor"] == "VS Code"
    
    # 6. Test profile prompt generation
    profile_prompt = await memory.build_profile_prompt()
    assert "USER PREFERENCES" in profile_prompt
    assert "editor: VS Code" in profile_prompt
    assert "SYSTEM" in profile_prompt
    assert "hardware: HP ZBook" in profile_prompt

@pytest.mark.asyncio
async def test_search_messages(db_path):
    memory = MemoryManager(db_path)
    await memory.init_db()
    
    session_id = "test_session_2"
    await memory.create_session(session_id, "test-model", "test-instructions")
    
    await memory.add_message(session_id, "user", "I need to deploy a docker container on the server.")
    await memory.add_message(session_id, "assistant", "You can use the docker-compose.yml file to run the service.")
    
    # Search for docker
    results = await memory.search_messages("docker")
    assert len(results) >= 2
    assert any("container" in r["content"] for r in results)
    assert any("compose" in r["content"] for r in results)
    
    # Search for server
    results_server = await memory.search_messages("server")
    assert len(results_server) >= 1
    assert "deploy" in results_server[0]["content"]
