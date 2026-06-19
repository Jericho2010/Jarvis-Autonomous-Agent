import os
from pathlib import Path

import pytest

from jarvis.config.models import (
    NIM_MODEL_BASKET,
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


def test_normalize_session_model_specific():
    assert normalize_session_model("house_party") == "house-party"
    assert (
        normalize_session_model("nvidia/mistralai/mistral-large-3-675b-instruct-2512")
        == "mistralai/mistral-large-3-675b-instruct-2512"
    )


def test_resolve_basket_model_strips_nvidia_prefix():
    resolved = resolve_basket_model("nvidia/stepfun-ai/step-3.7-flash")
    assert resolved == "stepfun-ai/step-3.7-flash"


def test_normalize_client_primary_maps_house_party():
    assert normalize_client_primary("house-party") == "house_party"
    assert (
        normalize_client_primary("nvidia/moonshotai/kimi-k2.6")
        == "moonshotai/kimi-k2.6"
    )


def test_apply_primary_model_on_client():
    client = StarkNIMChatClient(api_key="test-key")
    apply_primary_model(client, "house-party")
    assert client.primary_model == "house_party"

    apply_primary_model(client, "nvidia/mistralai/mistral-large-3-675b-instruct-2512")
    assert client.primary_model == "mistralai/mistral-large-3-675b-instruct-2512"


def test_select_failover_models_uses_resolved_primary(monkeypatch):
    monkeypatch.setattr(
        "jarvis.config.models.random.sample",
        lambda pool, count: pool[:count],
    )
    models = select_failover_models(
        "house-party",
        ["model-a", "model-b", "model-c"],
    )
    assert len(models) == 3

    models = select_failover_models(
        "nvidia/stepfun-ai/step-3.7-flash",
        list(NIM_MODEL_BASKET),
    )
    assert models[0] == "stepfun-ai/step-3.7-flash"


def test_workspace_root_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "custom.db"))
    assert get_workspace_root() == tmp_path.resolve()
    assert get_data_dir() == tmp_path / "data"
    assert get_skills_dir() == tmp_path / "skills"


def test_paths_default_to_repo_root():
    repo_root = Path(__file__).resolve().parents[1]
    assert get_workspace_root() == repo_root
