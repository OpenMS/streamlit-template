"""The Redis password from REDIS_PASSWORD is added to REDIS_URL."""
import importlib

from src.workflow.redis_auth import redis_url_with_password


def test_no_password_keeps_the_url(monkeypatch):
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)
    assert redis_url_with_password("redis://redis:6379/0") == "redis://redis:6379/0"
    monkeypatch.setenv("REDIS_PASSWORD", "")
    assert redis_url_with_password("redis://redis:6379/0") == "redis://redis:6379/0"


def test_password_is_added_and_quoted(monkeypatch):
    monkeypatch.setenv("REDIS_PASSWORD", "a/b@c")
    assert redis_url_with_password("redis://app-redis:6379/0") == "redis://:a%2Fb%40c@app-redis:6379/0"
    assert redis_url_with_password("rediss://host:6380") == "rediss://:a%2Fb%40c@host:6380"


def test_url_credentials_and_sockets_are_left_alone(monkeypatch):
    monkeypatch.setenv("REDIS_PASSWORD", "secret")
    assert redis_url_with_password("redis://:own@host:6379/0") == "redis://:own@host:6379/0"
    assert redis_url_with_password("unix:///tmp/redis.sock") == "unix:///tmp/redis.sock"


def test_rq_settings_reads_the_url(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("REDIS_PASSWORD", "pw")
    import src.workflow.rq_settings as settings
    assert importlib.reload(settings).REDIS_URL == "redis://:pw@redis:6379/0"
