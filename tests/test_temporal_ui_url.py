"""The demo view's Temporal UI link follows the injected base and namespace."""

import pytest

from agent_harness_demo import config


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("TEMPORAL_UI_URL", "TEMPORAL_UI_NAMESPACE", "TEMPORAL_ADDRESS"):
        monkeypatch.delenv(name, raising=False)


def test_platform_base_and_namespace(monkeypatch):
    monkeypatch.setenv("TEMPORAL_UI_URL", "https://cloud.temporal.io")
    monkeypatch.setenv("TEMPORAL_UI_NAMESPACE", "demo.acct")
    assert config.temporal_ui_url("default") == "https://cloud.temporal.io/namespaces/demo.acct"


def test_workspace_base_with_a_trailing_slash(monkeypatch):
    monkeypatch.setenv("TEMPORAL_UI_URL", "https://ws.example/_temporal/")
    monkeypatch.setenv("TEMPORAL_UI_NAMESPACE", "demo")
    assert config.temporal_ui_url("demo") == "https://ws.example/_temporal/namespaces/demo"


def test_base_alone_uses_the_connected_namespace(monkeypatch):
    monkeypatch.setenv("TEMPORAL_UI_URL", "https://ui.example")
    assert config.temporal_ui_url("demo") == "https://ui.example/namespaces/demo"


def test_a_namespace_url_is_used_as_it_is(monkeypatch):
    monkeypatch.setenv("TEMPORAL_UI_URL", "https://cloud.temporal.io/namespaces/demo.acct/")
    monkeypatch.setenv("TEMPORAL_UI_NAMESPACE", "other")
    assert config.temporal_ui_url("default") == "https://cloud.temporal.io/namespaces/demo.acct"


def test_nothing_set(monkeypatch):
    assert config.temporal_ui_url("default") == "http://localhost:8233/namespaces/default"
    monkeypatch.setenv("TEMPORAL_ADDRESS", "demo.acct.tmprl.cloud:7233")
    assert config.temporal_ui_url("demo.acct") == "https://cloud.temporal.io/namespaces/demo.acct"
