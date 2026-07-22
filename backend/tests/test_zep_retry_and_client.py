from types import SimpleNamespace

import pytest
from zep_cloud.core.api_error import ApiError as ZepApiError

from app.utils import zep
from app import config


def test_permanent_zep_errors_fail_without_retry():
    calls = []

    def operation():
        calls.append(True)
        raise ZepApiError(status_code=400, body={"message": "bad query"})

    with pytest.raises(ZepApiError):
        zep.call_zep_read_with_retry(
            operation,
            operation_name="permanent failure",
            sleep=lambda _seconds: None,
        )

    assert len(calls) == 1


def test_rate_limit_retry_respects_retry_after():
    calls = []
    sleeps = []

    def operation():
        calls.append(True)
        if len(calls) == 1:
            raise ZepApiError(
                status_code=429,
                headers={"Retry-After": "7"},
                body={"message": "slow down"},
            )
        return "ok"

    result = zep.call_zep_read_with_retry(
        operation,
        operation_name="rate limited read",
        sleep=sleeps.append,
    )

    assert result == "ok"
    assert len(calls) == 2
    assert sleeps == [7.0]


def test_zep_client_is_shared_and_uses_an_explicit_timeout(monkeypatch):
    created = []

    def fake_zep(**kwargs):
        created.append(kwargs)
        return SimpleNamespace(kwargs=kwargs)

    monkeypatch.delenv("ZEP_API_URL", raising=False)
    monkeypatch.setattr(zep, "Zep", fake_zep)
    zep.clear_zep_client_cache()

    first = zep.get_zep_client(" test-key ", timeout=12)
    second = zep.get_zep_client("test-key", timeout=12)

    assert first is second
    assert created == [{
        "api_key": "test-key",
        "base_url": zep.ZEP_CLOUD_BASE_URL,
        "timeout": 12.0,
    }]
    zep.clear_zep_client_cache()


def test_zep_client_rejects_self_hosted_endpoint_override(monkeypatch):
    monkeypatch.setenv("ZEP_API_URL", "https://example.invalid")

    with pytest.raises(ValueError, match="ZEP_API_URL"):
        zep.get_zep_client("test-key")


def test_malformed_timeout_config_is_reported_without_import_failure():
    value, error = config._parse_number(
        "ZEP_REQUEST_TIMEOUT_SECONDS",
        "not-a-number",
        default=30.0,
        cast=float,
    )

    assert value == 30.0
    assert "must be a number" in error


def test_zep_client_rejects_a_recorded_timeout_parse_error(monkeypatch):
    monkeypatch.setattr(
        zep.Config,
        "_ZEP_CONFIG_PARSE_ERRORS",
        ("ZEP_REQUEST_TIMEOUT_SECONDS must be a number",),
    )

    with pytest.raises(ValueError, match="must be a number"):
        zep.get_zep_client("test-key")
