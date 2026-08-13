from pathlib import Path

import pytest

from jarvis.config.models import (
    NIM_MODEL_BASKET,
    SUBAGENT_MODEL_BASKET,
    apply_primary_model,
    is_house_party,
    normalize_client_primary,
    normalize_session_model,
    resolve_basket_model,
    select_failover_models,
)
from jarvis.config.paths import get_data_dir, get_skills_dir, get_workspace_root
from jarvis.core.agent import StarkNIMChatClient


@pytest.mark.parametrize(
    "model",
    ["house-party", "house_party", "houseparty", "dynamic", "d", None, ""],
)
def test_is_house_party_aliases(model):
    assert is_house_party(model)


def test_nim_model_basket_order():
    assert NIM_MODEL_BASKET == [
        "z-ai/glm-5.2",
        "minimaxai/minimax-m3",
        "nvidia/nemotron-3-super-120b-a12b",
        "deepseek-ai/deepseek-v4-flash-0731",
        "stepfun-ai/step-3.7-flash",
    ]
    assert SUBAGENT_MODEL_BASKET == list(NIM_MODEL_BASKET)


def test_normalize_session_model_specific():
    assert normalize_session_model("house_party") == "house-party"
    assert (
        normalize_session_model("nvidia/stepfun-ai/step-3.7-flash")
        == "stepfun-ai/step-3.7-flash"
    )


def test_resolve_basket_model_strips_nvidia_prefix():
    resolved = resolve_basket_model("nvidia/stepfun-ai/step-3.7-flash")
    assert resolved == "stepfun-ai/step-3.7-flash"


def test_normalize_client_primary_maps_house_party():
    assert normalize_client_primary("house-party") == "house_party"
    assert (
        normalize_client_primary("nvidia/stepfun-ai/step-3.7-flash")
        == "stepfun-ai/step-3.7-flash"
    )


def test_apply_primary_model_on_client():
    client = StarkNIMChatClient(api_key="test-key")
    apply_primary_model(client, "house-party")
    assert client.primary_model == "house_party"

    apply_primary_model(client, "nvidia/stepfun-ai/step-3.7-flash")
    assert client.primary_model == "stepfun-ai/step-3.7-flash"


def test_select_failover_models_house_party_full_ordered_basket():
    models = select_failover_models("house-party", list(NIM_MODEL_BASKET))
    assert models == list(NIM_MODEL_BASKET)


def test_select_failover_models_pinned_then_remaining_in_order():
    models = select_failover_models(
        "nvidia/stepfun-ai/step-3.7-flash",
        list(NIM_MODEL_BASKET),
    )
    assert models[0] == "stepfun-ai/step-3.7-flash"
    assert models[1:] == [
        m for m in NIM_MODEL_BASKET if m != "stepfun-ai/step-3.7-flash"
    ]


def test_subagent_model_basket_excludes_eol_and_ultra():
    assert "deepseek-ai/deepseek-v4-pro" not in SUBAGENT_MODEL_BASKET
    assert "stepfun-ai/step-3.5-flash" not in SUBAGENT_MODEL_BASKET
    assert "nvidia/nemotron-mini-4b-instruct" not in SUBAGENT_MODEL_BASKET
    assert "nvidia/nemotron-3-ultra-550b-a55b" not in SUBAGENT_MODEL_BASKET
    assert "z-ai/glm-5.2" in SUBAGENT_MODEL_BASKET
    assert len(SUBAGENT_MODEL_BASKET) == 5


def test_workspace_root_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "custom.db"))
    assert get_workspace_root() == tmp_path.resolve()
    assert get_data_dir() == tmp_path / "data"
    assert get_skills_dir() == tmp_path / "skills"


def test_paths_default_to_repo_root():
    repo_root = Path(__file__).resolve().parents[1]
    assert get_workspace_root() == repo_root
