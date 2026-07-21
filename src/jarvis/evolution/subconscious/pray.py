import asyncio
import json
import logging
from datetime import datetime

from agent_framework._types import Message

from jarvis.config.models import apply_primary_model
from jarvis.config.paths import get_evolution_logs_dir, get_staging_dir
from jarvis.core.agent import StarkNIMChatClient
from jarvis.memory.memory_manager import MemoryManager
from jarvis.skills.skill_forge import forge_to_staging

from .common import bootstrap, require_api_key, setup_logging
from .forge_pipeline import parse_forge_response, validate_forge_proposal
from .saint import get_saint_of_the_day
from .staging import (
    ensure_staging_dirs,
    register_staged_skill,
    resolve_unique_name,
)
from .sync import sync_after_evolution

LOG = logging.getLogger("jarvis.evolution.pray")

PRAY_IDEATION_PROMPT = """[SYSTEM DIRECTIVE: PRAY — VIRTUE TO CAPABILITY]
You are JARVIS performing a nightly contemplative audit inspired by today's saint.

Saint of the Day: {name}
Core Virtues: {virtues}
Saint's Trials: {trial}

Contemplate how these virtues translate to practical enhancements for your role as Shaun's butler-engineer.
Most nights, no new skill is warranted.

Respond with JSON ONLY (no markdown fences):
{{"forge": false, "reason": "..."}}
OR if a clearly warranted reusable capability is identified:
{{"forge": true, "skill_name": "snake_case_name", "summary": "one line", "code": "complete python module with @tool functions", "test_command": "shell command that verifies the module"}}

Rules:
- forge:true only when a durable @tool skill is clearly needed
- test_command is mandatory when forge:true (e.g. python3 -c "import importlib.util; ...")
- code must import from agent_framework import tool
- prefer forge:false on quiet or ambiguous nights
"""


async def run_pray() -> None:
    bootstrap()
    setup_logging()
    LOG.info("Subconscious Pray // Starting...")
    print("JARVIS // Initiating Subconscious Pray cycle...")

    try:
        api_key = require_api_key()
    except RuntimeError as e:
        print(f"❌ {e}")
        return

    ensure_staging_dirs()
    log_dir = get_evolution_logs_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    log_path = log_dir / f"{now.strftime('%Y-%m-%d')}-pray.md"
    rel_log = f"data/evolution_logs/{log_path.name}"

    from jarvis.config.paths import get_db_path

    memory = MemoryManager(get_db_path())
    await memory.init_db()

    client = StarkNIMChatClient(api_key=api_key, base_url="https://integrate.api.nvidia.com/v1")
    apply_primary_model(client, "house-party")

    saint = await get_saint_of_the_day(client)
    print(f"✓ Pray: Contemplated {saint['name']} ({saint['virtues']})")

    meditation = ""
    try:
        med_prompt = (
            f"Write a brief hagiographical meditation (2 paragraphs) on {saint['name']}, "
            f"virtues ({saint['virtues']}), and trial: {saint['trial']}. "
            "Translate virtue to disciplined engineering stewardship for Jarvis."
        )
        med_resp = await client.get_response(
            [Message(role="user", contents=[med_prompt])],
            options={"temperature": 0.6},
        )
        meditation = med_resp.messages[0].contents[0].text if med_resp.messages else ""
    except Exception as e:
        LOG.exception("Pray meditation failed")
        meditation = f"Meditation unavailable: {e}"

    forge_result = "No skill staged."
    proposal_raw = ""
    try:
        ideation_prompt = PRAY_IDEATION_PROMPT.format(**saint)
        ideation_resp = await client.get_response(
            [Message(role="user", contents=[ideation_prompt])],
            options={"temperature": 0.5, "response_format": {"type": "json_object"}},
        )
        proposal_raw = ideation_resp.messages[0].contents[0].text if ideation_resp.messages else ""
        proposal = parse_forge_response(proposal_raw)

        if not proposal.get("forge"):
            reason = proposal.get("reason", "No capability gap identified.")
            forge_result = f"No skill staged: {reason}"
            print(f"✓ {forge_result}")
        else:
            err = validate_forge_proposal(proposal)
            if err:
                forge_result = f"Forge skipped: {err}"
                print(f"⚠️ {forge_result}")
            else:
                final_name, original_name = resolve_unique_name(proposal["skill_name"])
                staging_dir = get_staging_dir() / "pray"
                ok, report, test_passed = forge_to_staging(
                    final_name,
                    proposal["code"],
                    staging_dir,
                    proposal["test_command"],
                )
                if ok:
                    register_staged_skill(
                        name=final_name,
                        source="pray",
                        summary=proposal["summary"],
                        test_command=proposal["test_command"],
                        test_passed=test_passed,
                        evolution_log=rel_log,
                        original_name=original_name,
                    )
                    forge_result = f"Staged skill '{final_name}': {report}"
                    print(f"✓ {forge_result}")
                else:
                    forge_result = f"Staging forge failed: {report}"
                    print(f"⚠️ {forge_result}")
    except Exception as e:
        LOG.exception("Pray ideation failed")
        forge_result = f"Pray ideation failed: {e}"
        print(f"⚠️ {forge_result}")

    log_content = f"""# JARVIS // Subconscious Pray — {now.strftime('%Y-%m-%d')}

## Active Saint: {saint['name']}
### Virtues: {saint['virtues']}
### Spiritual Trials: {saint['trial']}

---

## Hagiographical Meditation
{meditation}

---

## Capability Proposal (structured)
```json
{proposal_raw or json.dumps({"forge": False, "reason": "no response"})}
```

---

## Staging Result
{forge_result}
"""
    log_path.write_text(log_content, encoding="utf-8")
    print(f"✓ Saved evolution log: {log_path.name}")

    sync_after_evolution(f"evolution: pray — {saint['name']} ({now.strftime('%Y-%m-%d')})")
    print("JARVIS // Subconscious Pray cycle complete.")


def main() -> None:
    asyncio.run(run_pray())


if __name__ == "__main__":
    main()
