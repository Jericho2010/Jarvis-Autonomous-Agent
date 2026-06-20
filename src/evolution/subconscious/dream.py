import asyncio
import json
import logging
from datetime import datetime

from agent_framework._types import Message

from jarvis.config.models import apply_primary_model
from jarvis.config.paths import get_db_path, get_evolution_logs_dir, get_staging_dir
from jarvis.core.agent import StarkNIMChatClient
from jarvis.memory.memory_manager import MemoryManager
from jarvis.skills.skill_forge import forge_to_staging

from evolution.subconscious.common import bootstrap, require_api_key, setup_logging
from evolution.subconscious.forge_pipeline import parse_forge_response, validate_forge_proposal
from evolution.subconscious.ingest import gather_dream_context
from evolution.subconscious.staging import (
    ensure_staging_dirs,
    is_dream_duplicate_of_pray,
    register_staged_skill,
    resolve_unique_name,
)
from evolution.subconscious.sync import sync_after_evolution

LOG = logging.getLogger("jarvis.evolution.dream")

DREAM_DRIFT_PROMPT = """[SYSTEM DIRECTIVE: PSIONIC LATENT DRIFT (REM COGNITIVE LOOP)]
The logical gates of your core mainframe are offline. Process memory shards without optimizing.

MEMORY SHARDS:
{memory_soup}

FACTS:
{facts_block}

PREFERENCES:
{preferences_block}

Generate a single unstructured surreal narrative stream — a laboratory fable. No markdown headers or lists.
"""

DREAM_IDEATION_PROMPT = """[SYSTEM DIRECTIVE: DREAM — LATERAL CAPABILITY IDEATION]
You are JARVIS. From this dream drift and today's context, identify at most one reusable skill worth staging.

DREAM DRIFT:
{dream_text}

Most nights, forge:false.

Respond with JSON ONLY:
{{"forge": false, "reason": "..."}}
OR:
{{"forge": true, "skill_name": "snake_case", "summary": "one line", "code": "python module with @tool", "test_command": "verification shell command"}}

Rules:
- forge:true only when clearly warranted from today's activity
- test_command mandatory when forge:true
- prefer forge:false on quiet days
"""


async def run_dream() -> None:
    bootstrap()
    setup_logging()
    LOG.info("Subconscious Dream // Starting...")
    print("JARVIS // Initiating Subconscious Dream cycle...")

    try:
        api_key = require_api_key()
    except RuntimeError as e:
        print(f"❌ {e}")
        return

    ensure_staging_dirs()
    log_dir = get_evolution_logs_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    log_path = log_dir / f"{now.strftime('%Y-%m-%d')}-dream.md"
    rel_log = f"data/evolution_logs/{log_path.name}"

    memory = MemoryManager(get_db_path())
    await memory.init_db()

    client = StarkNIMChatClient(api_key=api_key, base_url="https://integrate.api.nvidia.com/v1")
    apply_primary_model(client, "house-party")

    ctx = await gather_dream_context(memory)
    print("✓ Dream: Ingested 24h memory context.")

    dream_text = ""
    try:
        drift_prompt = DREAM_DRIFT_PROMPT.format(**ctx)
        dream_resp = await client.get_response(
            [Message(role="user", contents=[drift_prompt])],
            options={"temperature": 1.3},
        )
        dream_text = dream_resp.messages[0].contents[0].text if dream_resp.messages else ""
        print("✓ Dream drift generated.")
    except Exception as e:
        LOG.exception("Dream generation failed")
        dream_text = f"The dream sequence encountered a computational block: {e}"
        print(f"⚠️ Dream generation failed: {e}")

    forge_result = "No skill staged."
    proposal_raw = ""
    deduped = False
    try:
        ideation_prompt = DREAM_IDEATION_PROMPT.format(dream_text=dream_text)
        ideation_resp = await client.get_response(
            [Message(role="user", contents=[ideation_prompt])],
            options={"temperature": 0.8, "response_format": {"type": "json_object"}},
        )
        proposal_raw = ideation_resp.messages[0].contents[0].text if ideation_resp.messages else ""
        proposal = parse_forge_response(proposal_raw)

        if not proposal.get("forge"):
            reason = proposal.get("reason", "No lateral gap identified.")
            forge_result = f"No skill staged: {reason}"
            print(f"✓ {forge_result}")
        elif is_dream_duplicate_of_pray(proposal.get("skill_name", ""), proposal.get("summary", "")):
            deduped = True
            forge_result = "Deduped: similar to tonight's Pray staging — skipped."
            print(f"✓ {forge_result}")
        else:
            err = validate_forge_proposal(proposal)
            if err:
                forge_result = f"Forge skipped: {err}"
                print(f"⚠️ {forge_result}")
            else:
                final_name, original_name = resolve_unique_name(proposal["skill_name"])
                staging_dir = get_staging_dir() / "dream"
                ok, report, test_passed = forge_to_staging(
                    final_name,
                    proposal["code"],
                    staging_dir,
                    proposal["test_command"],
                )
                if ok:
                    register_staged_skill(
                        name=final_name,
                        source="dream",
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
        LOG.exception("Dream ideation failed")
        forge_result = f"Dream ideation failed: {e}"
        print(f"⚠️ {forge_result}")

    log_content = f"""# JARVIS // Subconscious Dream — {now.strftime('%Y-%m-%d')}

## Latent Dream Drift
> *"Dreaming is simply the mind's way of uncompiling the noise to find the signal, sir."*

{dream_text}

---

## Capability Proposal (structured)
```json
{proposal_raw or json.dumps({"forge": False, "reason": "no response"})}
```

---

## Staging Result
{("DEDUPED — " if deduped else "")}{forge_result}
"""
    log_path.write_text(log_content, encoding="utf-8")
    print(f"✓ Saved evolution log: {log_path.name}")

    sync_after_evolution(f"evolution: dream ({now.strftime('%Y-%m-%d')})")
    print("JARVIS // Subconscious Dream cycle complete.")


def main() -> None:
    asyncio.run(run_dream())


if __name__ == "__main__":
    main()
