from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.main as main
from app.core.config import Settings


def test_health_reports_working_database(monkeypatch):
    engine = MagicMock()
    monkeypatch.setattr(main, "engine", engine)
    with TestClient(main.app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "database": "healthy"}
    connection = engine.connect.return_value.__enter__.return_value
    assert str(connection.execute.call_args.args[0]) == "SELECT 1"


def test_health_returns_503_without_leaking_database_error(monkeypatch):
    engine = MagicMock()
    engine.connect.side_effect = RuntimeError("password=secret host=private")
    monkeypatch.setattr(main, "engine", engine)
    with TestClient(main.app) as client:
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unhealthy"}
    assert "secret" not in response.text


@pytest.mark.parametrize("field,value", [
    ("retrieval_max_attempts", 0),
    ("retrieval_retry_base_seconds", -1),
    ("retrieval_default_batch_limit", 0),
    ("retrieval_stale_running_minutes", -1),
    ("alpha_vantage_batch_daily_budget", -1),
    ("alpha_vantage_compact_points", 0),
    ("database_url", "   "),
])
def test_invalid_settings_fail_at_startup(field, value):
    values = {"database_url": "sqlite+pysqlite:///:memory:", field: value}
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, **values)
    assert any(item["loc"] == (field,) for item in error.value.errors())


def test_zero_daily_budget_is_valid_for_disabling_requests():
    settings = Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        alpha_vantage_batch_daily_budget=0,
    )
    assert settings.alpha_vantage_batch_daily_budget == 0
