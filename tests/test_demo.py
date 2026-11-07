import pytest

from services.demo import DEMO_NOTE, is_demo
from services.extractor import ExtractionFailed, make_client, saved_or_ask


def test_the_demo_is_off_unless_switched_on(monkeypatch):
    monkeypatch.delenv("CLARIO_DEMO", raising=False)
    assert not is_demo()
    for value in ("true", "1", "Yes", " TRUE "):
        monkeypatch.setenv("CLARIO_DEMO", value)
        assert is_demo(), value
    for value in ("", "false", "0", "no"):
        monkeypatch.setenv("CLARIO_DEMO", value)
        assert not is_demo(), value


def test_the_demo_never_connects_to_claude_even_with_a_key(monkeypatch):
    monkeypatch.setenv("CLARIO_DEMO", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-not-a-real-key")
    with pytest.raises(ExtractionFailed, match="public demo"):
        make_client()
    assert "never calls the AI service" in DEMO_NOTE


def test_saved_answers_still_replay_in_the_demo(monkeypatch, tmp_path):
    import json
    monkeypatch.setenv("CLARIO_DEMO", "true")
    saved = tmp_path / "labels.answer.json"
    saved.write_text(json.dumps({"input_sha256": "same input", "answer": {"files": []}}))

    def ask():
        return {"files": []}, make_client()  # would be refused: a saved answer must mean it is never asked

    assert saved_or_ask(saved, "same input", ask) == ({"files": []}, None, True)
    with pytest.raises(ExtractionFailed):
        saved_or_ask(saved, "different input", ask)  # anything new stops with the demo message
