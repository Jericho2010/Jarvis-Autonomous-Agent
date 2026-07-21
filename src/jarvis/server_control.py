import os
import sys
import socket
import time
import signal
import subprocess
import urllib.request
import json
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from jarvis.config.paths import get_data_dir

console = Console()
PID_FILE = get_data_dir() / "server.pid"

def check_jarvis_service(port: int) -> tuple[bool, bool]:
    """
    Checks if the port is open and returns if it runs J.A.R.V.I.S. and if it's open.
    Returns: (is_jarvis, is_open)
    """
    is_open = False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return False, False
            is_open = True
        url = f"http://127.0.0.1:{port}/health"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=1.0) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                return data.get("service") == "jarvis", True
    except Exception:
        pass
    return False, is_open

def find_free_port(start_port: int) -> int:
    """Scans for the next free port sequentially."""
    port = start_port
    while port < start_port + 100:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
        port += 1
    return start_port

def is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False

def get_running_server_info() -> tuple[Optional[int], Optional[int]]:
    if not PID_FILE.exists():
        return None, None
    try:
        lines = PID_FILE.read_text().strip().splitlines()
        if len(lines) >= 2:
            pid = int(lines[0])
            port = int(lines[1])
            if pid == -1:
                is_jarvis, _ = check_jarvis_service(port)
                if is_jarvis:
                    return pid, port
            elif is_pid_alive(pid):
                return pid, port
    except Exception:
        pass
    return None, None

def start_server_daemon(port: int) -> bool:
    pid, active_port = get_running_server_info()
    if pid is not None:
        console.print(f"[bold #FFD700]J.A.R.V.I.S. server is already running with PID {pid} on port {active_port}.[/]")
        return True
    
    # Check if the port is in use
    is_jarvis, is_open = check_jarvis_service(port)
    if is_open:
        if is_jarvis:
            console.print(f"[bold yellow]A J.A.R.V.I.S. server is already running on port {port} but wasn't tracked by this PID file. Re-registering...[/]")
            PID_FILE.parent.mkdir(parents=True, exist_ok=True)
            PID_FILE.write_text(f"-1\n{port}\n")
            return True
        else:
            console.print(f"[bold red]Error: Port {port} is occupied by another service.[/]")
            return False

    console.print(f"[bold #00F0FF]⬡ Starting J.A.R.V.I.S. server daemon on port {port}...[/]")
    log_dir = get_data_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = open(log_dir / "server.log", "a")
    
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "jarvis.server.app:app", "--host", "127.0.0.1", "--port", str(port)],
        stdout=log_file,
        stderr=log_file,
        start_new_session=True
    )
    
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(f"{proc.pid}\n{port}\n")
    
    for _ in range(30):
        time.sleep(0.5)
        is_jarvis_spawned, _ = check_jarvis_service(port)
        if is_jarvis_spawned:
            console.print(f"[bold green]✓ J.A.R.V.I.S. server daemon started successfully (PID {proc.pid}, port {port}).[/]")
            return True
            
    console.print(f"[bold red]❌ J.A.R.V.I.S. server failed to start within 15 seconds. Check logs at data/server.log[/]")
    try:
        proc.terminate()
        proc.wait(timeout=2.0)
    except Exception:
        pass
    if PID_FILE.exists():
        PID_FILE.unlink()
    return False

def stop_server_daemon() -> bool:
    pid, port = get_running_server_info()
    if pid is None:
        console.print("[yellow]J.A.R.V.I.S. server is not running (no active PID file).[/]")
        if PID_FILE.exists():
            PID_FILE.unlink()
        return False
        
    console.print(f"[bold #FFD700]Stopping J.A.R.V.I.S. server daemon (PID {pid})...[/]")
    
    if pid == -1:
        console.print("[yellow]PID is unregistered (-1). Clearing tracking file only.[/]")
        if PID_FILE.exists():
            PID_FILE.unlink()
        return True

    try:
        os.killpg(pid, signal.SIGTERM)
    except Exception:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
            
    for _ in range(10):
        time.sleep(0.5)
        if not is_pid_alive(pid):
            break
    else:
        console.print("[red]Server did not exit on SIGTERM. Escalating to SIGKILL...[/]")
        try:
            os.killpg(pid, signal.SIGKILL)
        except Exception:
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass
                
    if PID_FILE.exists():
        PID_FILE.unlink()
    console.print("[bold green]✓ J.A.R.V.I.S. server daemon stopped.[/]")
    return True

def status_server_daemon():
    pid, port = get_running_server_info()
    if pid is None:
        console.print("[bold red]J.A.R.V.I.S. Server Status: OFFLINE[/]")
        return
        
    is_jarvis, is_open = check_jarvis_service(port)
    if is_jarvis:
        console.print(Panel(
            f"[bold green]ONLINE[/]\n\n"
            f"[bold #FFD700]PID:[/] {pid}\n"
            f"[bold #FFD700]Port:[/] {port}\n"
            f"[bold #FFD700]URL:[/] http://localhost:{port}",
            title="J.A.R.V.I.S. Server Daemon Status",
            border_style="green"
        ))
    else:
        console.print(Panel(
            f"[bold yellow]STALE PID / UNRESPONSIVE[/]\n\n"
            f"[bold #FFD700]PID:[/] {pid}\n"
            f"[bold #FFD700]Port:[/] {port}\n"
            f"The server process is registered but health checks on port {port} are failing.",
            title="J.A.R.V.I.S. Server Daemon Status",
            border_style="yellow"
        ))
