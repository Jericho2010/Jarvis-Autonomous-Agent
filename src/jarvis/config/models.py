import random
from typing import List, Optional

NIM_MODEL_BASKET: List[str] = [
    "deepseek-ai/deepseek-v4-pro",
    "deepseek-ai/deepseek-v4-flash",
    "nvidia/nemotron-3-ultra-550b-a55b",
    "moonshotai/kimi-k2.6",
    "stepfun-ai/step-3.7-flash",
]

# Subagents run many tool rounds per turn; omit flaky/slow models from their rotation.
SUBAGENT_MODEL_BASKET: List[str] = [
    "deepseek-ai/deepseek-v4-pro",
    "deepseek-ai/deepseek-v4-flash",
    "moonshotai/kimi-k2.6",
    "stepfun-ai/step-3.7-flash",
]

HOUSE_PARTY_ALIASES = {
    "house-party",
    "house_party",
    "houseparty",
    "house",
    "h",
    "dynamic",
    "d",
}


def is_house_party(model: Optional[str]) -> bool:
    if model is None or not str(model).strip():
        return True
    normalized = model.strip().lower().replace("-", "_")
    return normalized in {alias.replace("-", "_") for alias in HOUSE_PARTY_ALIASES}


def resolve_basket_model(model: Optional[str]) -> Optional[str]:
    """Map an arbitrary model identifier to an exact NIM_MODEL_BASKET entry."""
    if not model or is_house_party(model):
        return None

    candidate = model.strip()
    if candidate in NIM_MODEL_BASKET:
        return candidate

    stripped = candidate
    if stripped.startswith("nvidia/"):
        stripped = stripped[len("nvidia/") :]
        if stripped in NIM_MODEL_BASKET:
            return stripped

    candidate_lower = candidate.lower()
    stripped_lower = stripped.lower()
    candidate_tail = candidate_lower.split("/")[-1]
    stripped_tail = stripped_lower.split("/")[-1]

    for basket_model in NIM_MODEL_BASKET:
        basket_lower = basket_model.lower()
        basket_tail = basket_lower.split("/")[-1]
        if candidate_lower == basket_lower or stripped_lower == basket_lower:
            return basket_model
        if candidate_tail == basket_tail or stripped_tail == basket_tail:
            return basket_model
        if basket_lower in candidate_lower or candidate_lower.endswith(basket_lower):
            return basket_model
        if basket_lower in stripped_lower or stripped_lower.endswith(basket_lower):
            return basket_model

    return None


def normalize_session_model(model: Optional[str]) -> str:
    """Normalize a model identifier for API/DB storage."""
    if is_house_party(model):
        return "house-party"
    resolved = resolve_basket_model(model)
    if resolved:
        return resolved
    return (model or "house-party").strip()


def normalize_client_primary(model: Optional[str]) -> str:
    """Normalize a model identifier for StarkNIMChatClient.primary_model."""
    if is_house_party(model):
        return "house_party"
    resolved = resolve_basket_model(model)
    return resolved or (model or "house_party").strip()


def apply_primary_model(client, model: Optional[str]) -> None:
    client.primary_model = normalize_client_primary(model)


def select_failover_models(primary_model: str, basket_pool: List[str]) -> List[str]:
    """Build the ordered model list for Stark Core Matrix failover."""
    pool = list(basket_pool)
    if not pool:
        return []

    if is_house_party(primary_model):
        sample_size = min(2, len(pool))
        return random.sample(pool, sample_size)

    resolved = resolve_basket_model(primary_model) or primary_model
    if resolved in pool:
        remaining = [model for model in pool if model != resolved]
        extras = random.sample(remaining, min(2, len(remaining)))
        return [resolved, *extras]

    sample_size = min(2, len(pool))
    return random.sample(pool, sample_size)
