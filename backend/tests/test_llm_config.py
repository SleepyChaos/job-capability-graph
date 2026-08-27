import json
from types import SimpleNamespace

from app.core.config import Settings
from app.infrastructure import llm


def test_default_deepseek_model_is_v4_flash() -> None:
    assert Settings.model_fields["llm_model"].default == "deepseek-v4-flash"


def test_chat_completions_request_uses_v4_flash(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {"choices": [{"message": {"content": '{"ok": true}'}}]}
            ).encode("utf-8")

    def fake_urlopen(request, *, timeout: int):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(
        llm,
        "get_settings",
        lambda: SimpleNamespace(
            llm_model="deepseek-v4-flash",
            llm_base_url="https://api.deepseek.com/v1",
            llm_api_key="test-key",
            llm_timeout_seconds=30,
        ),
    )
    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)

    content = llm._post_chat([{"role": "user", "content": "ping"}], json_mode=True)

    assert content == '{"ok": true}'
    assert captured["url"] == "https://api.deepseek.com/v1/chat/completions"
    assert captured["payload"] == {
        "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": "ping"}],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    assert captured["timeout"] == 30


def test_post_chat_explicit_timeout_overrides_global_setting(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {"choices": [{"message": {"content": "ok"}}]}
            ).encode("utf-8")

    def fake_urlopen(request, *, timeout: int):
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(
        llm,
        "get_settings",
        lambda: SimpleNamespace(
            llm_model="deepseek-v4-flash",
            llm_base_url="https://api.deepseek.com/v1",
            llm_api_key="test-key",
            llm_timeout_seconds=30,
        ),
    )
    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)

    content = llm._post_chat(
        [{"role": "user", "content": "ping"}],
        json_mode=False,
        timeout_seconds=180,
    )

    assert content == "ok"
    assert captured["timeout"] == 180
