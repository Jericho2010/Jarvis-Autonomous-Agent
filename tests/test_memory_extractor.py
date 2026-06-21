import pytest

from jarvis.memory.extractor import _format_transcript, _parse_extract_response
from jarvis.memory.memory_manager import MemoryManager


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test_memory_extractor.db"


def test_parse_extract_response_json_fence():
    raw = '```json\n{"session_summary": "Did rugby research.", "facts": []}\n```'
    data = _parse_extract_response(raw)
    assert data["session_summary"] == "Did rugby research."


def test_format_transcript_strips_thinking():
    messages = [
        {"role": "user", "content": "Hello"},
        {
            "role": "assistant",
            "content": "<think>\nplan\n</think>\nFinal answer.",
        },
    ]
    text = _format_transcript(messages)
    assert "plan" not in text
    assert "Final answer." in text


@pytest.mark.asyncio
async def test_profile_excludes_evolution_and_includes_summaries(db_path):
    memory = MemoryManager(db_path)
    await memory.init_db()

    await memory.upsert_fact("evolution", "reflection_1", "saint noise")
    await memory.upsert_fact("user", "name", "Shaun")
    await memory.upsert_fact("session_summary", "session_a", "Discussed rugby HUD.")
    await memory.upsert_fact("session_summary", "session_b", "Tested Friday launcher.")

    profile = await memory.build_profile_prompt()
    assert "evolution" not in profile.lower()
    assert "saint" not in profile.lower()
    assert "RECENT SESSIONS" in profile
    assert "rugby" in profile.lower()
    assert "COMPILED OPERATIONAL FACTS" in profile
    assert "Shaun" in profile


@pytest.mark.asyncio
async def test_get_session_history_returns_recent_messages(db_path):
    memory = MemoryManager(db_path)
    await memory.init_db()
    session_id = "hist_session"
    await memory.create_session(session_id, "m", "i")

    for i in range(5):
        await memory.add_message(session_id, "user", f"message-{i}")

    history = await memory.get_session_history(session_id, limit=2)
    assert len(history) == 2
    assert history[0]["content"] == "message-3"
    assert history[1]["content"] == "message-4"


@pytest.mark.asyncio
async def test_rehydration_block(db_path):
    memory = MemoryManager(db_path)
    await memory.init_db()
    session_id = "rehyd_session"
    await memory.create_session(session_id, "m", "i")
    await memory.add_message(session_id, "user", "Open Notes app")
    await memory.add_message(
        session_id,
        "assistant",
        "<think>\nhidden\n</think>\nNotes is not running.",
    )

    block = await memory.format_rehydration_block(session_id)
    assert "CONVERSATION RESTORED" in block
    assert "Open Notes" in block
    assert "Notes is not running" in block
    assert "hidden" not in block


@pytest.mark.asyncio
async def test_finalize_session_without_api_key(db_path):
    from jarvis.memory.extractor import finalize_session

    memory = MemoryManager(db_path)
    await memory.init_db()
    session_id = "fin_session"
    await memory.create_session(session_id, "m", "i")
    await memory.add_message(session_id, "user", "Research Springboks rugby news")
    await memory.add_message(session_id, "assistant", "Found three stories.")

    done = await finalize_session(memory, session_id, api_key="")
    assert done is True
    assert await memory.is_session_finalized(session_id)

    summaries = await memory.get_recent_session_summaries()
    assert any(s["subject"] == session_id for s in summaries)

    done_again = await finalize_session(memory, session_id, api_key="")
    assert done_again is False
