import sys
import asyncio
import httpx
from rich.console import Console
from rich.panel import Panel

from jarvis.completers import SLASH_COMMANDS
from jarvis.splash import print_help, print_tasks
from jarvis.skills.skill_forge import load_skills_from_dir
from jarvis.config.paths import get_skills_dir

console = Console()

async def handle_slash_command(tui, cmd: str) -> bool:
    parts = cmd.split(maxsplit=1)
    base = parts[0].lower()
    
    if base == "/help":
        print_help()
        return True
    elif base == "/clear":
        console.clear()
        return True
    elif base == "/new":
        async with httpx.AsyncClient() as client:
            try:
                payload = {}
                if tui.session_id:
                    payload["finalize_session_id"] = tui.session_id
                res = await client.post(
                    f"http://127.0.0.1:{tui.port}/v1/sessions",
                    json=payload,
                    timeout=5.0,
                )
                tui.set_session(res.json()["session_id"])
                try:
                    session_details = await client.get(f"http://127.0.0.1:{tui.port}/v1/sessions/{tui.session_id}", timeout=5.0)
                    tui.current_model = session_details.json().get("model") or "house-party"
                except Exception:
                    tui.current_model = "house-party"
                console.print(f"[bold #FFD700]✓ Started new dialogue session: {tui.session_id}[/]\n")
            except Exception as e:
                console.print(f"[bold red]❌ Failed to start new session:[/] {e}\n")
        return True
    elif base == "/tasks":
        await print_tasks()
        return True
    elif base == "/skills":
        skills_tools = load_skills_from_dir(get_skills_dir())
        lines = ["[bold]Loaded Skill Modules:[/bold]"]
        for s in skills_tools:
            lines.append(f"  [bold cyan]▪[/] {s.name} - {s.description}")
        console.print(Panel("\n".join(lines), title="System Skills Matrix", border_style="#FFD700"))
        return True
    elif base == "/models":
        async with httpx.AsyncClient() as client:
            try:
                res_models = await client.get(f"http://127.0.0.1:{tui.port}/v1/models", timeout=5.0)
                models = res_models.json()["models"]
                
                res_session = await client.get(f"http://127.0.0.1:{tui.port}/v1/sessions/{tui.session_id}", timeout=5.0)
                current_model = res_session.json().get("model") or "house-party"
                
                lines = ["[bold]Stark Core Matrix:[/bold]"]
                for i, m in enumerate(models):
                    prefix = "  "
                    if m == current_model:
                        prefix = "[bold cyan]⬡[/]"
                    
                    if m == "house-party":
                        lines.append(f"{prefix} {i+1}. {m} (Dynamic Multi-Model Protocol)")
                    else:
                        lines.append(f"{prefix} {i+1}. {m}")
                lines.append("\n[dim]Usage: /model <index|name|house_party>[/dim]")
                console.print(Panel("\n".join(lines), title="Stark Core Matrix Config", border_style="#FFD700"))
            except Exception as e:
                console.print(f"[bold red]❌ Failed to retrieve models:[/] {e}\n")
        return True
    elif base == "/model":
        if len(parts) < 2:
            return await handle_slash_command(tui, "/models")
            
        arg = parts[1].strip().lower()
        async with httpx.AsyncClient() as client:
            try:
                res_models = await client.get(f"http://127.0.0.1:{tui.port}/v1/models", timeout=5.0)
                models = res_models.json()["models"]
                
                matched_model = None
                if arg in ("house_party", "houseparty", "house", "h", "dynamic", "d"):
                    matched_model = "house-party"
                else:
                    try:
                        idx = int(arg) - 1
                        if 0 <= idx < len(models):
                            matched_model = models[idx]
                        else:
                            console.print("[bold #E63946]Invalid model index.[/bold #E63946]\n")
                            return True
                    except ValueError:
                        matched_model = next((m for m in models if arg in m.lower()), None)
                        
                if not matched_model:
                    console.print(f"[bold #E63946]Model '{arg}' not found in matrix.[/bold #E63946]\n")
                    return True
                    
                res_update = await client.post(
                    f"http://127.0.0.1:{tui.port}/v1/sessions/{tui.session_id}/model",
                    json={"model": matched_model},
                    timeout=5.0
                )
                if res_update.status_code == 200:
                    tui.current_model = matched_model
                    console.print(f"[bold #FFD700]✓ Primary routing set to: {matched_model}[/bold #FFD700]\n")
                else:
                    console.print(f"[bold red]❌ Failed to update model:[/] {res_update.text}\n")
            except Exception as e:
                console.print(f"[bold red]❌ Connection error:[/] {e}\n")
        return True
    elif base in ("/subagents", "/agents", "/sub"):
        lines = [
            "[bold #00F0FF]F.R.I.D.A.Y. (Tactical HUD Assistant)[/]",
            "  [bold #FFD700]▪ Focus:[/] Desktop automation, window management, screen captures & execution.",
            "  [bold #FFD700]▪ Model:[/] house-party (Stark Core Matrix)",
            "  [bold #FFD700]▪ Usage:[/] Ask J.A.R.V.I.S.: 'Ask Friday to take a screenshot' or 'Run command on Friday'.",
            "",
            "[bold #00F0FF]H.O.M.E.R. (Scholarly Research Intel)[/]",
            "  [bold #FFD700]▪ Focus:[/] Multi-engine web search, clean page structures, Playwright navigation & grounding.",
            "  [bold #FFD700]▪ Model:[/] house-party (Stark Core Matrix)",
            "  [bold #FFD700]▪ Usage:[/] Ask J.A.R.V.I.S.: 'Ask Homer to search the web for...'.",
            "",
            "[bold #00F0FF]P.L.A.T.O. (Logical Strategy Consultant)[/]",
            "  [bold #FFD700]▪ Focus:[/] Deep reasoning, static code analysis, complex problem solving & drafting.",
            "  [bold #FFD700]▪ Model:[/] house-party (Stark Core Matrix)",
            "  [bold #FFD700]▪ Usage:[/] Ask J.A.R.V.I.S.: 'Ask Plato to review my code in...'"
        ]
        console.print(Panel("\n".join(lines), title="Cognitive Sub-routines Matrix", border_style="#E63946"))
        return True
    elif base == "/switch":
        async with httpx.AsyncClient() as client:
            try:
                res = await client.get(f"http://127.0.0.1:{tui.port}/v1/sessions", timeout=5.0)
                res.raise_for_status()
                sessions = res.json()
                
                if len(parts) < 2:
                    lines = ["[bold]Existing Dialogue Sessions:[/bold]"]
                    for i, s in enumerate(sessions):
                        active_indicator = "  "
                        if s["session_id"] == tui.session_id:
                            active_indicator = "[bold cyan]⬡[/]"
                        title = s.get("title") or s["session_id"]
                        agent = s.get("agent_id", "jarvis").upper()
                        model = s.get("model") or "house-party"
                        lines.append(f"{active_indicator} {i+1}. {title} [dim]({agent} | {model} | {s['session_id']})[/dim]")
                    lines.append("\n[dim]Usage: /switch <index|session_id>[/dim]")
                    console.print(Panel("\n".join(lines), title="Stark Dialogue Archive", border_style="#FFD700"))
                    return True
                
                arg = parts[1].strip()
                matched_session = None
                try:
                    idx = int(arg) - 1
                    if 0 <= idx < len(sessions):
                        matched_session = sessions[idx]
                    else:
                        console.print("[bold #E63946]Invalid session index.[/bold #E63946]\n")
                        return True
                except ValueError:
                    matched_session = next((s for s in sessions if arg == s["session_id"]), None)
                    if not matched_session:
                        matched_session = next((s for s in sessions if s["session_id"].startswith(arg)), None)
                        
                if not matched_session:
                    console.print(f"[bold #E63946]Session '{arg}' not found.[/bold #E63946]\n")
                    return True
                
                tui.set_session(matched_session["session_id"], title=matched_session.get("title"))
                tui.current_model = matched_session.get("model") or "house-party"
                tui.active_agent_id = matched_session.get("agent_id") or "jarvis"
                
                console.print(f"[bold #FFD700]✓ Switched to session: {tui.session_title} ({tui.session_id})[/bold #FFD700]\n")
            except Exception as e:
                console.print(f"[bold red]❌ Failed to switch session:[/] {e}\n")
        return True
    elif base == "/agent":
        if len(parts) < 2:
            console.print(f"[bold #FFD700]Active Session Agent:[/] [bold cyan]{getattr(tui, 'active_agent_id', 'jarvis').upper()}[/bold cyan]")
            console.print("[dim]Usage: /agent <jarvis|friday|homer|plato>[/dim]\n")
            return True
        
        agent_id = parts[1].strip().lower()
        if agent_id not in ("jarvis", "friday", "homer", "plato"):
            console.print(f"[bold #E63946]Invalid agent ID '{agent_id}'. Must be one of: jarvis, friday, homer, plato.[/bold #E63946]\n")
            return True
            
        async with httpx.AsyncClient() as client:
            try:
                res = await client.post(
                    f"http://127.0.0.1:{tui.port}/v1/sessions/{tui.session_id}/switch-agent",
                    json={"agent_id": agent_id},
                    timeout=5.0
                )
                res.raise_for_status()
                tui.active_agent_id = agent_id
                console.print(f"[bold #FFD700]✓ Active agent set to: {agent_id.upper()}[/bold #FFD700]\n")
            except Exception as e:
                console.print(f"[bold red]❌ Failed to switch agent:[/] {e}\n")
        return True
    elif base == "/voicemode":
        async with httpx.AsyncClient() as client:
            try:
                if len(parts) < 2:
                    res = await client.get(f"http://127.0.0.1:{tui.port}/v1/voice/status", timeout=5.0)
                    res.raise_for_status()
                    status = res.json()
                    state = "ON" if status.get("enabled") else "OFF"
                    voice = status.get("voice") or "unresolved"
                    gender = status.get("gender") or "unknown"
                    lines = [
                        f"[bold]Voice Mode:[/bold] {state}",
                        f"[bold]Voice:[/bold] {voice} ({gender})",
                        f"[bold]TTS:[/bold] {'available' if status.get('tts_available') else 'unavailable'}",
                        f"[bold]STT:[/bold] {'available' if status.get('stt_available') else 'unavailable'}",
                    ]
                    warning = status.get("persona_warning")
                    if warning:
                        lines.append(f"[bold #E63946]Warning:[/bold #E63946] {warning}")
                    if status.get("error"):
                        lines.append(f"[dim]Error: {status['error']}[/dim]")
                    lines.append("\n[dim]Usage: /voicemode on|off[/dim]")
                    console.print(Panel("\n".join(lines), title="Voice Mode Status", border_style="#FFD700"))
                    return True

                arg = parts[1].strip().lower()
                if arg in ("on", "true", "1", "yes", "enable"):
                    enabled = True
                elif arg in ("off", "false", "0", "no", "disable"):
                    enabled = False
                else:
                    console.print("[bold #E63946]Usage: /voicemode [on|off][/bold #E63946]\n")
                    return True

                res = await client.post(
                    f"http://127.0.0.1:{tui.port}/v1/voice/mode",
                    json={"enabled": enabled},
                    timeout=5.0,
                )
                if res.status_code == 503:
                    console.print(f"[bold #E63946]Voice services unavailable:[/] {res.text}\n")
                    return True
                res.raise_for_status()
                if enabled:
                    console.print(
                        "[bold #FFD700]✓ Voice mode enabled.[/] "
                        "Jarvis will speak in a male English butler voice; "
                        "use the Web HUD microphone to dictate.\n"
                    )
                else:
                    console.print("[bold #FFD700]✓ Voice mode disabled.[/]\n")
            except Exception as e:
                console.print(f"[bold red]❌ Failed to update voice mode:[/] {e}\n")
        return True
    elif base == "/evolve":
        from jarvis.evolution.subconscious import staging as evo_staging
        from jarvis.evolution.subconscious.sync import sync_after_evolution

        evo_staging.ensure_staging_dirs()

        if len(parts) < 2:
            pending = evo_staging.list_pending()
            if not pending:
                console.print(
                    Panel(
                        "No pending staged skills.\n\n[dim]/evolve archive — rejected history\n/evolve show <name>[/dim]",
                        title="Evolution Staging",
                        border_style="#FFD700",
                    )
                )
                return True
            lines = ["[bold]Pending staged skills:[/bold]"]
            for p in pending:
                test = "pass" if p.get("test_passed") else "fail"
                lines.append(
                    f"  [cyan]{p['name']}[/] [{p.get('source')}] "
                    f"forged {str(p.get('forged_at', '?'))[:10]} test:{test}"
                )
                lines.append(f"    {p.get('summary', '')}")
            lines.append(
                "\n[dim]/evolve approve <name|all>  /evolve reject <name>  "
                "/evolve archive  /evolve show <name>[/dim]"
            )
            console.print(Panel("\n".join(lines), title="Evolution Staging", border_style="#FFD700"))
            return True

        sub_parts = parts[1].split(maxsplit=1)
        action = sub_parts[0].lower()
        arg = sub_parts[1].strip() if len(sub_parts) > 1 else ""

        if action == "approve":
            if not arg:
                console.print("[bold #E63946]Usage: /evolve approve <name|all>[/]\n")
                return True
            if arg.lower() == "all":
                pending = evo_staging.list_pending()
                if not pending:
                    console.print("[dim]No pending skills to approve.[/]\n")
                    return True
                count, msgs = evo_staging.approve_all()
                for m in msgs:
                    console.print(f"  {m}")
                if count:
                    sync_after_evolution(f"evolution: approve all ({count} skills)")
                console.print(f"\n[bold #FFD700]✓ Promoted {count} skill(s) to live.[/]\n")
                return True
            ok, msg = evo_staging.approve_skill(arg)
            if ok:
                sync_after_evolution(f"evolution: approve {arg}")
                console.print(f"[bold #FFD700]✓ {msg}[/]\n")
            else:
                console.print(f"[bold #E63946]{msg}[/]\n")
            return True

        if action == "reject":
            if not arg:
                console.print("[bold #E63946]Usage: /evolve reject <name>[/]\n")
                return True
            ok, msg = evo_staging.reject_skill(arg)
            if ok:
                sync_after_evolution(f"evolution: reject {arg}")
                console.print(f"[bold #FFD700]✓ {msg}[/]\n")
            else:
                console.print(f"[bold #E63946]{msg}[/]\n")
            return True

        if action == "archive":
            rejected = evo_staging.list_rejected()
            if not rejected:
                console.print(Panel("No rejected skills in archive.", title="Evolution Archive", border_style="#FFD700"))
                return True
            lines = ["[bold]Rejected skills (archaeology):[/bold]"]
            for r in rejected:
                test = "pass" if r.get("test_passed") else "fail"
                lines.append(
                    f"  [cyan]{r['name']}[/] [{r.get('source')}] "
                    f"forged {str(r.get('forged_at', '?'))[:10]} "
                    f"rejected {str(r.get('rejected_at', '?'))[:10]} test:{test}"
                )
                lines.append(f"    {r.get('summary', '')}")
            lines.append("\n[dim]/evolve show <name> for detail[/dim]")
            console.print(Panel("\n".join(lines), title="Evolution Archive", border_style="#FFD700"))
            return True

        if action == "show":
            if not arg:
                console.print("[bold #E63946]Usage: /evolve show <name>[/]\n")
                return True
            console.print(
                Panel(
                    evo_staging.format_skill_show(arg),
                    title=f"Evolution // {arg}",
                    border_style="#FFD700",
                )
            )
            return True

        console.print("[bold #E63946]Unknown /evolve action.[/] Use approve, reject, archive, or show.\n")
        return True
    elif base == "/exit":
        tui.shutdown()
        sys.exit(0)
        
    return False
