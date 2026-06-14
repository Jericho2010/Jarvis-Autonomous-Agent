#!/usr/bin/env python3
import asyncio
import os
import sys
import httpx
import subprocess
import time

PORT = 8008
BASE_URL = f"http://127.0.0.1:{PORT}"

async def listen_stream(client_id, session_id, events_received):
    url = f"{BASE_URL}/v1/sessions/{session_id}/stream?client_id={client_id}"
    print(f"[INFO] Client '{client_id}' starting SSE stream listener...")
    async with httpx.AsyncClient(timeout=None) as client:
        try:
            async with client.stream("GET", url) as response:
                event_type = None
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("event:"):
                        event_type = line.split(":", 1)[1].strip()
                    elif line.startswith("data:"):
                        data_str = line.split(":", 1)[1].strip()
                        if event_type == "user_message":
                            print(f"[RECV] Client '{client_id}' received user_message: {data_str}")
                            events_received.append((client_id, data_str))
        except asyncio.CancelledError:
            print(f"[INFO] Client '{client_id}' listener stopped.")
        except Exception as e:
            print(f"[ERROR] Client '{client_id}' listener error: {e}")

async def main():
    print("=== J.A.R.V.I.S. Reciprocal Mirroring Verification ===")

    # 1. Start server daemon if not running
    print("[INFO] Checking if J.A.R.V.I.S. server is running...")
    server_running = False
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{BASE_URL}/health")
            if res.status_code == 200:
                print(f"[INFO] J.A.R.V.I.S. server is already running on port {PORT}.")
                server_running = True
    except httpx.ConnectError:
        pass

    spawned = False
    if not server_running:
        print(f"[INFO] Starting J.A.R.V.I.S. server daemon on port {PORT}...")
        # Start daemon
        subprocess.run([".venv/bin/python", "-m", "jarvis.cli", "server", "start", "--port", str(PORT)], cwd="/home/shaun/jarvis", check=True)
        spawned = True
        # Wait for server to start
        for i in range(10):
            try:
                async with httpx.AsyncClient() as client:
                    res = await client.get(f"{BASE_URL}/health")
                    if res.status_code == 200:
                        print("[INFO] J.A.R.V.I.S. server daemon started successfully.")
                        server_running = True
                        break
            except httpx.ConnectError:
                pass
            await asyncio.sleep(0.5)

    if not server_running:
        print("[FAIL] Failed to contact/start J.A.R.V.I.S. server daemon.", file=sys.stderr)
        sys.exit(1)

    # 2. Create session
    print("[INFO] Creating a new session...")
    async with httpx.AsyncClient() as client:
        res = await client.post(f"{BASE_URL}/v1/sessions")
        if res.status_code != 200:
            print(f"[FAIL] Failed to create session: {res.text}", file=sys.stderr)
            sys.exit(1)
        session_id = res.json()["session_id"]
        print(f"[INFO] Created session ID: {session_id}")

    # 3. Setup client streams
    tui_events = []
    web_events = []
    
    tui_task = asyncio.create_task(listen_stream("tui", session_id, tui_events))
    web_task = asyncio.create_task(listen_stream("web", session_id, web_events))
    
    # Wait for connections to establish
    await asyncio.sleep(1.0)

    try:
        # 4. TUI sends a message
        print("\n--- Test Case 1: TUI sends a message ---")
        async with httpx.AsyncClient() as client:
            print("[SEND] TUI posting message: 'Hello from TUI'")
            res = await client.post(
                f"{BASE_URL}/v1/sessions/{session_id}/chat",
                json={"message": "Hello from TUI", "client_id": "tui"}
            )
            assert res.status_code == 200, f"Chat post failed: {res.text}"

        # Wait for SSE queues to process
        await asyncio.sleep(1.0)

        # Check: Web should receive it, TUI should NOT.
        tui_got_msg = any("Hello from TUI" in e[1] for e in tui_events)
        web_got_msg = any("Hello from TUI" in e[1] for e in web_events)
        
        print(f"[RESULT] TUI received own message: {tui_got_msg} (Expected: False)")
        print(f"[RESULT] Web received TUI message: {web_got_msg} (Expected: True)")
        
        if tui_got_msg or not web_got_msg:
            print("[FAIL] Test Case 1 failed: Mirroring/Exclusion logic incorrect.")
            sys.exit(1)
        print("[PASS] Test Case 1 passed.")

        # 5. Web sends a message
        print("\n--- Test Case 2: Web sends a message ---")
        async with httpx.AsyncClient() as client:
            print("[SEND] Web posting message: 'Hello from Web'")
            res = await client.post(
                f"{BASE_URL}/v1/sessions/{session_id}/chat",
                json={"message": "Hello from Web", "client_id": "web"}
            )
            assert res.status_code == 200, f"Chat post failed: {res.text}"

        # Wait for SSE queues to process
        await asyncio.sleep(1.0)

        # Check: TUI should receive it, Web should NOT.
        tui_got_msg_web = any("Hello from Web" in e[1] for e in tui_events)
        web_got_msg_web = any("Hello from Web" in e[1] for e in web_events)

        print(f"[RESULT] Web received own message: {web_got_msg_web} (Expected: False)")
        print(f"[RESULT] TUI received Web message: {tui_got_msg_web} (Expected: True)")

        if web_got_msg_web or not tui_got_msg_web:
            print("[FAIL] Test Case 2 failed: Mirroring/Exclusion logic incorrect.")
            sys.exit(1)
        print("[PASS] Test Case 2 passed.")

    finally:
        # Clean up stream listeners
        tui_task.cancel()
        web_task.cancel()
        await asyncio.gather(tui_task, web_task, return_exceptions=True)

        if spawned:
            print("\n[INFO] Stopping J.A.R.V.I.S. server daemon...")
            subprocess.run([".venv/bin/python", "-m", "jarvis.cli", "server", "stop"], cwd="/home/shaun/jarvis")

    print("\n[SUCCESS] Reciprocal mirroring and server-side exclusion is fully verified and functional!")
    sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())
