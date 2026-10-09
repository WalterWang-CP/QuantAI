from unittest.mock import Mock

import httpx
import pytest

from app.core.config import settings
from app.providers.errors import ProviderRateLimitError, ProviderRequestError, ProviderTemporaryError
from app.providers.sec import SECClient, decode_sec_json


@pytest.fixture(autouse=True)
def isolated_client_state(monkeypatch):
    SECClient._cache.clear()
    SECClient._next_request = 0
    now = [0.0]
    waits = []
    monkeypatch.setattr("app.providers.sec.time.monotonic", lambda: now[0])
    def sleep(delay):
        waits.append(delay)
        now[0] += delay
    monkeypatch.setattr("app.providers.sec.time.sleep", sleep)
    monkeypatch.setattr(settings, "sec_request_interval_seconds", 0.5)
    monkeypatch.setattr(settings, "sec_max_attempts", 3)
    monkeypatch.setattr(settings, "sec_cache_ttl_seconds", 300)
    yield waits
    SECClient._cache.clear()
    SECClient._next_request = 0


def response(status=200, body=b'{"cik":320193}', headers=None):
    return httpx.Response(status, content=body, headers=headers or {"content-type": "application/json"})


def test_requires_contact_user_agent():
    with pytest.raises(ProviderRequestError, match="SEC_USER_AGENT"):
        SECClient(user_agent="QuantAI")
    with pytest.raises(ProviderRequestError):
        SECClient(user_agent="QuantAI test@example.com\nInjected: yes")


def test_fetch_uses_cik_headers_timeout_and_caches(monkeypatch):
    get = Mock(return_value=response())
    monkeypatch.setattr("app.providers.sec.httpx.get", get)
    client = SECClient(user_agent="QuantAI test@example.com")
    first = client.fetch_submissions("320193")
    assert client.fetch_submissions("0000320193") is first
    assert get.call_count == 1
    assert get.call_args.args[0] == "https://data.sec.gov/submissions/CIK0000320193.json"
    assert get.call_args.kwargs["headers"]["User-Agent"] == "QuantAI test@example.com"
    assert get.call_args.kwargs["timeout"] == settings.sec_timeout_seconds
    assert not get.call_args.kwargs["follow_redirects"]


def test_rate_slots_are_shared_across_client_instances(monkeypatch, isolated_client_state):
    monkeypatch.setattr("app.providers.sec.httpx.get", Mock(return_value=response()))
    SECClient(user_agent="QuantAI test@example.com").fetch_submissions("320193")
    SECClient(user_agent="QuantAI test@example.com").fetch_company_facts("320193")
    assert isolated_client_state == [0.5]


def test_cache_expiry_fetches_again(monkeypatch):
    get = Mock(return_value=response())
    monkeypatch.setattr("app.providers.sec.httpx.get", get)
    client = SECClient(user_agent="QuantAI test@example.com")
    client.fetch_submissions("320193")
    monkeypatch.setattr("app.providers.sec.time.monotonic", lambda: 301.0)
    client.fetch_submissions("320193")
    assert get.call_count == 2


def test_transient_failure_is_retried(monkeypatch):
    get = Mock(side_effect=[response(503), response()])
    monkeypatch.setattr("app.providers.sec.httpx.get", get)
    result = SECClient(user_agent="QuantAI test@example.com").fetch_submissions("320193")
    assert decode_sec_json(result)["cik"] == 320193
    assert get.call_count == 2


def test_network_failure_is_retried(monkeypatch):
    get = Mock(side_effect=[httpx.ConnectError("offline"), response()])
    monkeypatch.setattr("app.providers.sec.httpx.get", get)
    SECClient(user_agent="QuantAI test@example.com").fetch_submissions("320193")
    assert get.call_count == 2


@pytest.mark.parametrize("status", [403, 404, 302])
def test_permanent_errors_are_not_retried(monkeypatch, status):
    get = Mock(return_value=response(status))
    monkeypatch.setattr("app.providers.sec.httpx.get", get)
    with pytest.raises(ProviderRequestError, match=str(status)):
        SECClient(user_agent="QuantAI test@example.com").fetch_submissions("320193")
    assert get.call_count == 1


def test_long_retry_after_sets_shared_cooldown(monkeypatch):
    get = Mock(return_value=response(429, headers={"retry-after": "120"}))
    monkeypatch.setattr("app.providers.sec.httpx.get", get)
    with pytest.raises(ProviderRateLimitError):
        SECClient(user_agent="QuantAI test@example.com").fetch_submissions("320193")
    with pytest.raises(ProviderRateLimitError, match="cooldown"):
        SECClient(user_agent="QuantAI test@example.com").fetch_company_facts("320193")
    assert get.call_count == 1


def test_rate_limit_retry_after_is_honored(monkeypatch, isolated_client_state):
    get = Mock(side_effect=[response(429, headers={"retry-after": "3"}), response()])
    monkeypatch.setattr("app.providers.sec.httpx.get", get)
    SECClient(user_agent="QuantAI test@example.com").fetch_submissions("320193")
    assert 3 in isolated_client_state
    assert get.call_count == 2


def test_invalid_json_is_not_cached(monkeypatch):
    get = Mock(return_value=response(body=b'<html>blocked</html>'))
    monkeypatch.setattr("app.providers.sec.httpx.get", get)
    with pytest.raises(ProviderTemporaryError):
        SECClient(user_agent="QuantAI test@example.com").fetch_submissions("320193")
    assert get.call_count == 3
    assert not SECClient._cache


def test_history_filename_cannot_escape_sec_endpoint():
    with pytest.raises(ProviderRequestError, match="filename"):
        SECClient(user_agent="QuantAI test@example.com").fetch_history_file("320193", "../other.json")


def test_json_decimal_values_are_not_rounded(monkeypatch):
    get = Mock(return_value=response(body=b'{"value":123456789.12345678901234567890}'))
    monkeypatch.setattr("app.providers.sec.httpx.get", get)
    result = SECClient(user_agent="QuantAI test@example.com").fetch_company_facts("320193")
    assert str(decode_sec_json(result)["value"]) == "123456789.12345678901234567890"
