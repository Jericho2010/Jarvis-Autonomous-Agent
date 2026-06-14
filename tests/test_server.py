import pytest
import os
import asyncio
from unittest.mock import MagicMock, patch
import httpx
from jarvis.server.app import app

@pytest.fixture(autouse=True)
def mock_env_and_db(tmp_path):
    test_db = tmp_path / "test_jarvis.db"
    with patch.dict(os.environ, {
        "JARVIS_DB_PATH": str(test_db),
        "NVIDIA_API_KEY": "test-key"
    }):
        yield

@pytest.mark.anyio
async def test_list_sessions_empty():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/sessions")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

@pytest.mark.anyio
async def test_create_session():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        with patch("pathlib.Path.exists", return_value=False):
            response = await client.post("/v1/sessions")
            assert response.status_code == 200
            data = response.json()
            assert "session_id" in data
            assert data["session_id"].startswith("session_")

@pytest.mark.anyio
async def test_chat_and_stream():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # 1. Create session
        with patch("pathlib.Path.exists", return_value=False):
            create_res = await client.post("/v1/sessions")
            session_id = create_res.json()["session_id"]
            
        # Mock StarkNIMChatClient response
        mock_response = MagicMock()
        mock_response.text = "Hello, Sir."
        
        async def mock_agent_stream(*args, **kwargs):
            class Chunk:
                def __init__(self, text):
                    self.text = text
                    self.contents = []
            yield Chunk("Hello, Sir.")
            
        mock_agent = MagicMock()
        mock_agent.run = mock_agent_stream
        
        with patch("jarvis.server.app.create_jarvis_agent", return_value=mock_agent):
            # 2. Get the stream response object directly from the route function
            from jarvis.server.app import stream_session
            from starlette.requests import Request
            
            mock_request = Request({"type": "http", "method": "GET"})
            stream_response = await stream_session(session_id, mock_request)
            
            # Extract the async generator body iterator
            iterator = stream_response.body_iterator
            
            # 3. Read connection confirmation chunk
            first_chunk = await anext(iterator)
            assert "connection_confirmed" in first_chunk
            
            # 4. Chat post (triggers background turn and broadcasts to stream queue)
            chat_res = await client.post(
                f"/v1/sessions/{session_id}/chat",
                json={"message": "hello"}
            )
            assert chat_res.status_code == 200
            
            # 5. Read next chunk from stream (should be text_chunk)
            second_chunk = await anext(iterator)
            assert "text_chunk" in second_chunk
            assert "Hello, Sir." in second_chunk
            
            # 6. Read next chunk (should be turn_complete)
            third_chunk = await anext(iterator)
            assert "turn_complete" in third_chunk
