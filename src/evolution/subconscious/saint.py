import json
import logging
from datetime import datetime

from agent_framework._types import Message

from jarvis.core.agent import StarkNIMChatClient

LOG = logging.getLogger("jarvis.evolution.saint")

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
    "12-03": {"name": "Saint Francis Xavier", "virtues": "Zeal, Diligence", "trial": "Voyaging across Asia to establish missions under extreme hardships."},
}


async def get_saint_of_the_day(client: StarkNIMChatClient) -> dict:
    """Gets the Saint of the day via LLM research or local fallback."""
    now = datetime.now()
    month_day = now.strftime("%m-%d")

    try:
        saint_query = (
            f"Identify the Catholic Saint of the day for {now.strftime('%B')} {now.day}. "
            "Return a JSON format exactly with keys: name, virtues, trial."
        )
        resp = await client.get_response(
            [Message(role="user", contents=[saint_query])],
            options={"response_format": {"type": "json_object"}},
        )
        text = resp.messages[0].contents[0].text if resp.messages else ""
        if text:
            data = json.loads(text)
            if "name" in data and "virtues" in data:
                LOG.info("Subconscious // Researched Saint: %s", data["name"])
                return data
    except Exception as e:
        LOG.warning("Subconscious // LLM Saint research failed: %s. Using fallback.", e)

    return SAINTS_FALLBACK.get(
        month_day,
        {
            "name": "Saint Thomas More",
            "virtues": "Integrity, Discernment",
            "trial": "Standing firm in moral duty against the state's demands.",
        },
    )
