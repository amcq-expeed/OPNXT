import importlib
import sys
import types

import pytest


def _reload_events(monkeypatch, *, url=None, redis_module=None):
    monkeypatch.delenv("REDIS_URL", raising=False)
    if url is not None:
        monkeypatch.setenv("REDIS_URL", url)
    if redis_module is not None:
        monkeypatch.setitem(sys.modules, "redis", redis_module)
    else:
        stub = types.SimpleNamespace(Redis=types.SimpleNamespace(from_url=lambda *args, **kwargs: None))
        monkeypatch.setitem(sys.modules, "redis", stub)
    sys.modules.pop("src.orchestrator.infrastructure.events", None)
    return importlib.import_module("src.orchestrator.infrastructure.events")


def test_publish_event_no_url_returns_quietly(monkeypatch):
    stub = types.SimpleNamespace(Redis=types.SimpleNamespace(from_url=lambda *args, **kwargs: None))
    module = _reload_events(monkeypatch, redis_module=stub)
    assert module._get_publisher() is None
    module.publish_event("test", {"payload": "ignored"})


class FakeRedisClient:
    attempt = 0
    published = []
    publish_should_fail = False

    def ping(self):
        if FakeRedisClient.attempt == 0:
            FakeRedisClient.attempt += 1
            raise Exception("connect failed")

    def publish(self, channel, payload):
        FakeRedisClient.published.append((channel, payload))
        if FakeRedisClient.publish_should_fail:
            FakeRedisClient.publish_should_fail = False
            raise Exception("publish failed")


def test_redis_publisher_recovers_after_connection_failure(monkeypatch):
    FakeRedisClient.attempt = 0
    FakeRedisClient.published = []
    FakeRedisClient.publish_should_fail = False

    def from_url(url, socket_timeout=0.5):
        return FakeRedisClient()

    redis_module = types.SimpleNamespace(Redis=types.SimpleNamespace(from_url=staticmethod(from_url)))

    module = _reload_events(monkeypatch, url="redis://localhost", redis_module=redis_module)
    publisher = module._get_publisher()
    assert publisher is not None

    module.publish_event("code.generated", {"value": 1})
    assert FakeRedisClient.attempt == 1  # first ping failed once
    assert FakeRedisClient.published[-1][0] == "opnxt.events.code.generated"

    FakeRedisClient.publish_should_fail = True
    module.publish_event("code.generated", {"value": 2})  # should swallow publish exception
    assert module.load_event_client() is publisher
