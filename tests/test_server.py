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
            
            # 5. Read next chunk from stream (should be user_message)
            second_chunk = await anext(iterator)
            assert "user_message" in second_chunk
            assert "hello" in second_chunk
            
            # 6. Read next chunk (should be text_chunk)
            third_chunk = await anext(iterator)
            assert "text_chunk" in third_chunk
            assert "Hello, Sir." in third_chunk
            
            # 7. Read next chunk (should be turn_complete)
            fourth_chunk = await anext(iterator)
            assert "turn_complete" in fourth_chunk

@pytest.mark.anyio
async def test_health_endpoint():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy", "service": "jarvis"}

def test_check_jarvis_service_and_find_free_port():
    from jarvis.cli import check_jarvis_service, find_free_port
    import socket
    
    # 1. check_jarvis_service should return False for closed port
    closed_port = 59999
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        while s.connect_ex(('127.0.0.1', closed_port)) == 0:
            closed_port -= 1
            
    assert check_jarvis_service(closed_port) == (False, False)
    
    # 2. find_free_port should return the first closed port
    free_port = find_free_port(closed_port)
    assert free_port == closed_port


def test_daemon_lifecycle(tmp_path):
    from jarvis.cli import is_pid_alive, get_running_server_info, start_server_daemon, stop_server_daemon, PID_FILE
    import signal
    from unittest.mock import patch, MagicMock
    
    test_pid_file = tmp_path / "server.pid"
    
    with patch("jarvis.cli.PID_FILE", test_pid_file):
        # 1. PID file doesn't exist initially
        pid, port = get_running_server_info()
        assert pid is None
        assert port is None
        
        # 2. Test is_pid_alive
        with patch("os.kill") as mock_kill:
            # Alive case
            mock_kill.return_value = None
            assert is_pid_alive(12345) is True
            mock_kill.assert_called_once_with(12345, 0)
            
            # Dead case (ProcessLookupError)
            mock_kill.reset_mock()
            mock_kill.side_effect = ProcessLookupError()
            assert is_pid_alive(12345) is False
            
        # 3. Test start_server_daemon success
        mock_proc = MagicMock()
        mock_proc.pid = 99999
        
        with patch("subprocess.Popen", return_value=mock_proc) as mock_popen, \
             patch("jarvis.cli.check_jarvis_service", side_effect=[(False, False), (True, True)]) as mock_check, \
             patch("time.sleep") as mock_sleep:
             
            success = start_server_daemon(8008)
            assert success is True
            assert test_pid_file.exists()
            assert test_pid_file.read_text() == "99999\n8008\n"
            
            # Check info
            with patch("jarvis.cli.is_pid_alive", return_value=True):
                pid, port = get_running_server_info()
                assert pid == 99999
                assert port == 8008
                
        # 4. Test stop_server_daemon
        with patch("os.killpg") as mock_killpg, \
             patch("jarvis.cli.is_pid_alive", side_effect=[True, False]), \
             patch("time.sleep") as mock_sleep:
             
            success = stop_server_daemon()
            assert success is True
            mock_killpg.assert_called_once_with(99999, signal.SIGTERM)
            assert not test_pid_file.exists()

@pytest.mark.anyio
async def test_session_detail_and_model_endpoints():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        with patch("pathlib.Path.exists", return_value=False):
            create_res = await client.post("/v1/sessions")
            session_id = create_res.json()["session_id"]
            
        res_detail = await client.get(f"/v1/sessions/{session_id}")
        assert res_detail.status_code == 200
        assert res_detail.json()["session_id"] == session_id
        assert res_detail.json()["model"] == "house-party"
        
        res_models = await client.get("/v1/models")
        assert res_models.status_code == 200
        assert "models" in res_models.json()
        assert "house-party" in res_models.json()["models"]
        
        res_set_model = await client.post(
            f"/v1/sessions/{session_id}/model",
            json={"model": "nvidia/deepseek-ai/deepseek-v4-pro"}
        )
        assert res_set_model.status_code == 200
        assert res_set_model.json()["model"] == "deepseek-ai/deepseek-v4-pro"

        res_detail_updated = await client.get(f"/v1/sessions/{session_id}")
        assert res_detail_updated.json()["model"] == "deepseek-ai/deepseek-v4-pro"

        res_invalid_model = await client.post(
            f"/v1/sessions/{session_id}/model",
            json={"model": "totally-unknown-model"},
        )
        assert res_invalid_model.status_code == 400

@pytest.mark.anyio
async def test_session_history_endpoint():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        with patch("pathlib.Path.exists", return_value=False):
            create_res = await client.post("/v1/sessions")
            session_id = create_res.json()["session_id"]
            
        res_hist = await client.get(f"/v1/sessions/{session_id}/history")
        assert res_hist.status_code == 200
        assert res_hist.json() == []

@pytest.mark.anyio
async def test_subagents_detail_endpoint():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res_agent = await client.get("/v1/subagents/friday")
        assert res_agent.status_code == 200
        data = res_agent.json()
        assert data["name"] == "FRIDAY"
        assert "model" in data
        assert "instructions" in data
        assert "tools" in data
        
        res_missing = await client.get("/v1/subagents/invalid-agent")
        assert res_missing.status_code == 404

@pytest.mark.anyio
async def test_file_upload_and_content_delivery():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        with patch("pathlib.Path.exists", return_value=False):
            create_res = await client.post("/v1/sessions")
            session_id = create_res.json()["session_id"]
            
        file_payload = {"file": ("test.txt", b"Hello from attached test file content", "text/plain")}
        upload_res = await client.post(
            f"/v1/sessions/{session_id}/files",
            files=file_payload
        )
        assert upload_res.status_code == 200
        upload_data = upload_res.json()
        assert "id" in upload_data
        assert upload_data["filename"] == "test.txt"
        assert upload_data["bytes"] == len("Hello from attached test file content")
        
        file_id = upload_data["id"]
        
        content_res = await client.get(
            f"/v1/sessions/{session_id}/files/{file_id}/content"
        )
        assert content_res.status_code == 200
        assert content_res.content == b"Hello from attached test file content"

@pytest.mark.anyio
async def test_switch_session_agent():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        with patch("pathlib.Path.exists", return_value=False):
            create_res = await client.post("/v1/sessions")
            session_id = create_res.json()["session_id"]
            
        switch_res = await client.post(
            f"/v1/sessions/{session_id}/switch-agent",
            json={"agent_id": "homer"}
        )
        assert switch_res.status_code == 200
        assert switch_res.json()["agent_id"] == "homer"
        
        detail_res = await client.get(f"/v1/sessions/{session_id}")
        assert detail_res.status_code == 200
        assert detail_res.json()["agent_id"] == "homer"

@pytest.mark.anyio
async def test_dynamic_session_title_synthesis():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        with patch("pathlib.Path.exists", return_value=False):
            create_res = await client.post("/v1/sessions")
            session_id = create_res.json()["session_id"]
            
        detail_res = await client.get(f"/v1/sessions/{session_id}")
        assert detail_res.status_code == 200
        assert detail_res.json()["title"] == session_id
        
        mock_agent = MagicMock()
        async def mock_agent_stream(*args, **kwargs):
            class Chunk:
                def __init__(self, text):
                    self.text = text
                    self.contents = []
            yield Chunk("response")
        mock_agent.run = mock_agent_stream
        
        with patch("jarvis.server.app.create_jarvis_agent", return_value=mock_agent):
            chat_res = await client.post(
                f"/v1/sessions/{session_id}/chat",
                json={"message": "Test dialogue title generation prompt"}
            )
            assert chat_res.status_code == 200
            
            await asyncio.sleep(0.2)
            
            detail_updated = await client.get(f"/v1/sessions/{session_id}")
            assert detail_updated.status_code == 200
            assert detail_updated.json()["title"] == "Test dialogue title generation prompt"



