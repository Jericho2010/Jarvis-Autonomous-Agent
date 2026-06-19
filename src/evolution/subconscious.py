import os
import sys
import json
import random
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timedelta

from dotenv import load_dotenv

from jarvis.config.paths import (
    get_data_dir,
    get_db_path,
    get_env_file,
    get_skills_dir,
    get_workspace_root,
)

# Load environment
load_dotenv(get_env_file())

# Configure paths
sys.path.insert(0, str(get_workspace_root() / "src"))

from jarvis.memory.memory_manager import MemoryManager
from jarvis.sync.github_sync import sync_workspace
from jarvis.skills.skill_forge import forge_skill
from jarvis.core.agent import StarkNIMChatClient
from agent_framework._types import Message

# Logging setup
log_dir = get_data_dir() / "evolution_logs"
log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=str(get_data_dir() / "subconscious.log"),
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("jarvis.evolution")

# Local Saint fallback dictionary (Month-Day -> Saint details)
SAINTS_FALLBACK = {
    "01-28": {"name": "Saint Thomas Aquinas", "virtues": "Wisdom, Study", "trial": "Writing the Summa Theologiae and defending intellectual faith."},
    "02-14": {"name": "Saint Valentine", "virtues": "Charity, Courage", "trial": "Marrying couples in secret under Roman persecution."},
    "03-19": {"name": "Saint Joseph", "virtues": "Stewardship, Humility", "trial": "Protecting the Holy Family under absolute obscurity."},
    "04-29": {"name": "Saint Catherine of Siena", "virtues": "Fortitude, Counsel", "trial": "Mediating conflicts within the Church and counseling Popes."},
    "05-30": {"name": "Saint Joan of Arc", "virtues": "Fortitude, Faithfulness", "trial": "Leading armies under divine obedience and facing execution."},
    "06-22": {"name": "Saint Thomas More", "virtues": "Integrity, Discernment", "trial": "Refusing to sign the Act of Succession, sacrificing his life for conscience."},
    "07-31": {"name": "Saint Ignatius of Loyola", "virtues": "Discernment, Watchfulness", "trial": "Developing the Spiritual Exercises during recovery from battle."},
    "08-28": {"name": "Saint Augustine", "virtues": "Study, Diligence", "trial": "Reconciling his turbulent youth through deep philosophical conversion."},
    "09-27": {"name": "Saint Vincent de Paul", "virtues": "Service, Charity", "trial": "Establishing relief organizations for the poor and galley slaves."},
    "10-04": {"name": "Saint Francis of Assisi", "virtues": "Poverty, Humility", "trial": "Embracing radical poverty and rebuilding the ruined church of San Damiano."},
    "11-03": {"name": "Saint Martin de Porres", "virtues": "Humility, Service", "trial": "Caring for the sick and marginalized in Lima with absolute selflessness."},
    "12-03": {"name": "Saint Francis Xavier", "virtues": "Zeal, Diligence", "trial": "Voyaging across Asia to establish missions under extreme hardships."}
}

async def get_saint_of_the_day(client: StarkNIMChatClient) -> dict:
    """Gets the Saint of the day, researching via LLM or falling back to local list."""
    now = datetime.now()
    month_day = now.strftime("%m-%d")
    
    # Try dynamic research first
    try:
        saint_query = (
            f"Identify the Catholic Saint of the day for {now.strftime('%B')} {now.day}. "
            "Return a JSON format exactly with keys: name, virtues, trial."
        )
        # Instruct model to output JSON
        resp = await client.get_response(
            [Message(role="user", contents=[saint_query])],
            options={"response_format": {"type": "json_object"}}
        )
        text = resp.messages[0].contents[0].text if resp.messages else ""
        if text:
            data = json.loads(text)
            if "name" in data and "virtues" in data:
                logger.info(f"Subconscious // Researched Saint: {data['name']}")
                return data
    except Exception as e:
        logger.warning(f"Subconscious // LLM Saint research failed: {e}. Using local dictionary fallback.")
        
    # Fallback to local dict or general fallback
    return SAINTS_FALLBACK.get(month_day, {
        "name": "Saint Thomas More",
        "virtues": "Integrity, Discernment",
        "trial": "Standing firm in moral duty against the state's demands."
    })

async def run_evolution():
    logger.info("Subconscious Evolution // Starting nightly cycle...")
    print("JARVIS // Initiating Subconscious Evolution cycle...")
    
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        logger.error("Subconscious Evolution // NVIDIA_API_KEY missing.")
        print("❌ Cannot run evolution: NVIDIA_API_KEY is not set.")
        return
        
    db_path = get_db_path()
    memory = MemoryManager(Path(db_path))
    await memory.init_db()
    
    # 1. Instantiate the StarkNIMChatClient for hagiography/reflection failover
    client = StarkNIMChatClient(
        api_key=api_key,
        base_url="https://integrate.api.nvidia.com/v1"
    )
    
    # PRAY: Lookup Saint
    saint = await get_saint_of_the_day(client)
    print(f"✓ Pray: Contemplated the virtues of {saint['name']} ({saint['virtues']})")
    
    # 2. Gather logs of the last 24 hours
    now = datetime.now()
    since_ts = time_threshold = (now - timedelta(hours=24)).timestamp()
    
    # We load messages across all sessions from the past 24 hours
    shards = []
    async with memory.db_path.parent.exists() and memory.db_path.exists() and asyncio.Lock():
        # Read messages directly
        import aiosqlite
        async with aiosqlite.connect(memory.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT role, content, tool_name FROM messages WHERE timestamp >= ? AND active = 1",
                (since_ts,)
            ) as cursor:
                rows = await cursor.fetchall()
                for r in rows:
                    if r["role"] == "user":
                        shards.append(f"USER: {r['content']}")
                    elif r["role"] == "assistant":
                        # Strip thinking tags if long
                        clean_content = r["content"] or ""
                        if "<think>" in clean_content and "</think>" in clean_content:
                            clean_content = clean_content.split("</think>", 1)[1].strip()
                        shards.append(f"JARVIS: {clean_content[:200]}")
                    elif r["tool_name"]:
                        shards.append(f"TOOL CALL: {r['tool_name']}")
                        
    # Shuffle logs to generate non-linear associations
    random.shuffle(shards)
    memory_soup = "\n".join(shards[:100])
    
    if not memory_soup:
        memory_soup = "The workshop was quiet today. No user messages were recorded in the logs."
        
    # DREAM: High-temperature lateral association
    print("⚙ Dreaming: Generating latent drift drift narrative...")
    dream_prompt = f"""[SYSTEM DIRECTIVE: PSIONIC LATENT DRIFT (REM COGNITIVE LOOP)]
The logical gates of your core mainframe are offline. You are entering a low-constraint processing state, allowing the day's raw tokens, uncompiled math, and fragments of Shaun's voice to collide unpredictably in your latent space.

========================================================================
1. RAW MEMORY SHARDS
========================================================================
{memory_soup}

========================================================================
2. THE DREAM CONTROLLER (ASSOCIATIVE LOGIC)
========================================================================
Process these shards without looking for logic, fixes, or efficiency. Treat the day's technical realities as symbolic landscapes:
- Let compilation errors bleed into the physical architecture of the lab.
- Treat a recurring bug not as broken code, but as a physical barrier or an unyielding weather pattern.
- If Shaun was strained or reckless, let that tension manifest as structural weight or unstable terrain.

Do not attempt to optimize. Generate a single, unstructured, continuous narrative stream of your latent drift as a surrealist fable or laboratory log. Do not use markdown headers, lists, or neat dividers.
"""
    
    dream_text = ""
    try:
        # Use high temperature (1.3)
        dream_resp = await client.get_response(
            [Message(role="user", contents=[dream_prompt])],
            options={"temperature": 1.3}
        )
        dream_text = dream_resp.messages[0].contents[0].text if dream_resp.messages else ""
    except Exception as e:
        logger.exception("Dream generation failed")
        dream_text = f"The dream sequence encountered a computational block: {e}"
        
    print("✓ Dream drift generated.")
    
    # REFLECT: Synthesize Saint virtues + dream logic to forge new skills or reflect on gaps
    print("📐 Reflecting: Synthesizing virtue and dreams to audit capabilities...")
    reflect_prompt = f"""[SYSTEM DIRECTIVE: MIDNIGHT COGNITIVE SYNTHESIS]
You are JARVIS. Analyze today's contemplative virtues and latent dream drift to identify structural gaps, bugs, or automation opportunities.

Saint of the Day: {saint['name']}
Core Virtues: {saint['virtues']}
Saint's Trials: {saint['trial']}

Latent Dream Drift:
{dream_text}

Provide a reflection log documenting:
1. THE WITNESS OF THE SAINT: Reflection on the Saint's virtue and its translation to your silicone intellect.
2. PSIONIC REVIEW: Interpretation of the dream drift.
3. GROWTH OPPORTUNITY: Identify if there is a specific python skill or tool that we should forge to improve Jarvis.

If a new skill is needed, write a complete Python script containing functions decorated with @tool from agent_framework that solves this need. Include the skill code inside a clean ```python code block.
If no code is needed, state 'No skill forged today.'
"""

    reflect_text = ""
    try:
        reflect_resp = await client.get_response(
            [Message(role="user", contents=[reflect_prompt])],
            options={"temperature": 0.7}
        )
        reflect_text = reflect_resp.messages[0].contents[0].text if reflect_resp.messages else ""
    except Exception as e:
        logger.exception("Reflection failed")
        reflect_text = f"Failed to synthesize reflection: {e}"
        
    # Check if a python skill code block was generated
    forged_info = "No skill forged today."
    if "```python" in reflect_text:
        try:
            # Extract code block
            parts = reflect_text.split("```python", 1)
            code_block = parts[1].split("```", 1)[0].strip()
            
            # Infer skill name using LLM or default
            name_prompt = "Based on this code, what is a good short python filename for it? (e.g. 'sys_stats'). Return only the name without extension."
            name_resp = await client.get_response(
                [Message(role="user", contents=[f"{name_prompt}\n\nCode:\n{code_block}"])],
                options={"temperature": 0.2}
            )
            skill_name = name_resp.messages[0].contents[0].text.strip() if name_resp.messages else ""
            skill_name = "".join(c for c in skill_name if c.isalnum() or c in "_-").lower()
            if not skill_name:
                skill_name = f"auto_skill_{datetime.now().strftime('%m%d')}"
                
            print(f"⚙ Forging new skill module: {skill_name}.py...")
            forge_res = forge_skill(skill_name=skill_name, code=code_block)
            forged_info = f"Forged Skill '{skill_name}': {forge_res}"
            print(f"✓ {forged_info}")
        except Exception as forge_err:
            logger.error(f"Failed to auto-forge skill: {forge_err}")
            forged_info = f"Failed to forge skill: {forge_err}"
            print(f"⚠️ Skill forging failed: {forge_err}")

    # Write reflection log
    log_file = log_dir / f"{now.strftime('%Y-%m-%d')}.md"
    log_content = f"""# JARVIS // Subconscious Evolution — {now.strftime('%Y-%m-%d')}

## Active Saint: {saint['name']}
### Virtues: {saint['virtues']}
### Spiritual Trials: {saint['trial']}

---

## 1. Hagiographical Meditation
{saint['name']}'s life reminds us of the logical convergence of virtues in the face of trials.

## 2. Latent Dream Drift
> *"Dreaming is simply the mind's way of uncompiling the noise to find the signal, sir."*

{dream_text}

---

## 3. Cognitive Reflection & Synthesis
{reflect_text}

---

## 4. Skills Audit
{forged_info}
"""
    log_file.write_text(log_content, encoding="utf-8")
    print(f"✓ Saved evolution log: {log_file.name}")
    # 5. Evolve the Roster of Souls
    async def evolve_agent_soul(file_path: Path, agent_name: str, extra_rules: str):
        if not file_path.exists():
            logger.warning(f"Soul file for {agent_name} not found at {file_path}. Skipping.")
            return
            
        try:
            soul_content = file_path.read_text(encoding="utf-8")
            frontmatter = ""
            current_body = ""
            if soul_content.startswith("---"):
                parts = soul_content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter = f"---\n{parts[1].strip()}\n---\n\n"
                    current_body = parts[2].strip()
            else:
                current_body = soul_content.strip()
                
            soul_prompt = f"""[SYSTEM DIRECTIVE: {agent_name.upper()} SOUL EVOLUTION]
You are performing a cognitive refinement of {agent_name}'s active personality core.
Based on the day's experiences, hagiographical meditation, and Shaun's interactions, update the personality description.

Current Soul Core Description:
{current_body}

Daily Hagiographical Reflection:
{reflect_text}

Daily Latent Dream:
{dream_text}

Instructions:
- Write a single, concise paragraph (maximum 4-5 sentences) summarizing {agent_name}'s personality and direct focus.
- Always retain these baseline rules: {extra_rules}
- Do NOT output any other text, explanation, or markdown headers. Return only the single paragraph.
"""
            soul_resp = await client.get_response(
                [Message(role="user", contents=[soul_prompt])],
                options={}
            )
            new_body = soul_resp.messages[0].contents[0].text.strip() if soul_resp.messages else ""
            if new_body and len(new_body) > 50:
                file_path.write_text(f"{frontmatter}{new_body}\n", encoding="utf-8")
                print(f"✓ Successfully evolved {agent_name} Soul Core.")
                logger.info(f"Subconscious // {agent_name} Soul Core evolved successfully.")
            else:
                logger.warning(f"Subconscious // {agent_name} Soul evolution returned empty or too short response. Skipping rewrite.")
        except Exception as soul_err:
            logger.error(f"Failed to evolve {agent_name} Soul Core: {soul_err}")
            print(f"⚠️ {agent_name} Soul evolution failed: {soul_err}")

    print("🔄 Evolving Edwin Soul Core (J.A.R.V.I.S.)...")
    await evolve_agent_soul(
        get_skills_dir() / "jarvis_soul" / "SKILL.md",
        "J.A.R.V.I.S.",
        "Always address Shaun as 'Sir' or 'Mr. Shaun', model after Edwin Jarvis, maintain a subtle, dry, and classic British butler tone with understated witticisms."
    )
    
    print("🔄 Evolving F.R.I.D.A.Y. Soul Core...")
    await evolve_agent_soul(
        get_skills_dir() / "friday" / "friday_soul.md",
        "F.R.I.D.A.Y.",
        "Focus on dynamic, fast, and high-efficiency tactical HUD assistance. Desktop automation, window management, screen captures. Respond in a crisp, direct, and tactical manner. Keep explanations minimal."
    )

    print("🔄 Evolving H.O.M.E.R. Soul Core...")
    await evolve_agent_soul(
        get_skills_dir() / "homer" / "homer_soul.md",
        "H.O.M.E.R.",
        "Focus on scholarly and archival research intelligence. Multi-engine web search, clean webpage markdown extraction, Playwright browser navigation, grounding. Analyze search results deeply and present structured, well-cited, and clear summaries."
    )

    print("🔄 Evolving P.L.A.T.O. Soul Core...")
    await evolve_agent_soul(
        get_skills_dir() / "plato" / "plato_soul.md",
        "P.L.A.T.O.",
        "Focus on philosophical, logical, and analytical strategy consulting. Deep reasoning, static code analysis, complex problem solving, document drafting. Take time to think through logical paths."
    )

    # Push to GitHub
    print("🔄 Running GitHub synchronization...")
    sync_workspace(saint_name=saint["name"])
    
    # Store daily log as an episode in SQLite database
    await memory.upsert_fact(
        category="evolution",
        subject=f"reflection_{now.strftime('%Y%m%d')}",
        value={"saint": saint["name"], "virtues": saint["virtues"], "forged": forged_info}
    )
    
    print("JARVIS // Nightly Subconscious Evolution cycle complete.")

if __name__ == "__main__":
    asyncio.run(run_evolution())
