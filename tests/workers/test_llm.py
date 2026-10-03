from pathlib import Path

from homelab_creator.config import load_settings
from homelab_creator.workers.llm import DEFAULT_BASE_URL, DEFAULT_MODEL, base_url, chat_model, live_llm_enabled, model_id, reasoning_effort


def test_pytest_forces_heuristics():
    assert live_llm_enabled() is False


def test_empty_conf_uses_defaults():
    assert base_url() == DEFAULT_BASE_URL
    assert model_id() == DEFAULT_MODEL
    assert reasoning_effort() == "medium"
    assert "airouter.ch" in DEFAULT_BASE_URL


def test_conf_yaml_key_model_effort(tmp_path: Path, monkeypatch):
    path = tmp_path / "conf.yaml"
    path.write_text(
        "airouter:\n  api_key: sk-from-file\n  model: DeepSeek-V4-Flash\n  reasoning_effort: xhigh\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOMELAB_CONF", str(path))
    settings = load_settings()
    assert settings.api_key == "sk-from-file"
    assert settings.model == "DeepSeek-V4-Flash"
    assert settings.reasoning_effort == "xhigh"


def test_chat_model_openai_compatible(monkeypatch):
    monkeypatch.setenv("AIROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("HOMELAB_MODEL", "Qwen3.8")
    model = chat_model()
    assert "airouter.ch" in (model.openai_api_base or "")
    extra = model.extra_body or {}
    assert extra.get("reasoning_effort") == "medium"


def test_refine_notes_keeps_search_on_timeout(monkeypatch):
    from homelab_creator.spec.models import LabSpec
    from homelab_creator.workers.agents import refine_notes_with_agent

    class Boom:
        def invoke(self, *_a, **_k):
            raise TimeoutError("Request timed out.")

    monkeypatch.setattr(
        "homelab_creator.workers.agents.create_research_agent",
        lambda **_k: Boom(),
    )
    monkeypatch.setattr("homelab_creator.workers.agents.live_llm_enabled", lambda: True)
    spec = LabSpec(research={"opted_in": True, "notes": ["legacy auth"], "citations": ["https://example.invalid/a"]})
    out = refine_notes_with_agent(spec)
    assert out.research.notes == ["legacy auth"]
    assert out.research.citations == ["https://example.invalid/a"]


def test_deep_agent_factories(monkeypatch):
    created = []

    class Dummy:
        def invoke(self, *_a, **_k):
            return {}

    def fake_create_deep_agent(**kwargs):
        created.append(kwargs)
        return Dummy()

    monkeypatch.setattr("deepagents.create_deep_agent", fake_create_deep_agent)
    monkeypatch.setenv("AIROUTER_API_KEY", "sk-test")
    from homelab_creator.workers.agents import create_planner_agent, create_research_agent

    planner = create_planner_agent(model="unused")
    research = create_research_agent(model="unused")
    assert planner is not None
    assert research is not None
    assert created[0]["name"] == "vuln-planner"
    assert created[1]["name"] == "research-worker"
    assert any(getattr(t, "name", "") == "commit_notes" or getattr(t, "name", None) for t in created[1]["tools"])
