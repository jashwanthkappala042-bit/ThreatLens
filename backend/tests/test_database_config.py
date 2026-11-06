"""Tests for database URL normalization and driver selection."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.engine import make_url

from app.config import BACKEND_DIR, _database_url


def test_sqlite_fallback_when_unset_or_empty(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    expected_path = (BACKEND_DIR / "instance" / "threatlens.db").as_posix()
    expected_url = f"sqlite:///{expected_path}"

    assert _database_url() == expected_url
    assert _database_url("") == expected_url
    assert _database_url("   ") == expected_url

    parsed = make_url(_database_url())
    assert parsed.get_backend_name() == "sqlite"
    assert parsed.database == expected_path


def test_sqlite_explicit_urls_preserved():
    in_memory = "sqlite:///:memory:"
    assert _database_url(in_memory) == in_memory

    custom_path = "sqlite:///custom/storage/app.db"
    assert _database_url(custom_path) == custom_path


def test_postgres_legacy_url_normalized_to_psycopg2():
    legacy_url = "postgres://neon_user:secret_pwd@ep-cool-123.ap-southeast-1.aws.neon.tech:5432/neondb"
    normalized = _database_url(legacy_url)

    assert normalized.startswith("postgresql+psycopg2://")
    parsed = make_url(normalized)
    assert parsed.get_backend_name() == "postgresql"
    assert parsed.get_driver_name() == "psycopg2"
    assert parsed.username == "neon_user"
    assert parsed.password == "secret_pwd"
    assert parsed.host == "ep-cool-123.ap-southeast-1.aws.neon.tech"
    assert parsed.port == 5432
    assert parsed.database == "neondb"


def test_postgresql_url_converted_to_psycopg2():
    standard_url = "postgresql://neon_user:secret_pwd@ep-cool-123.ap-southeast-1.aws.neon.tech:5432/neondb"
    normalized = _database_url(standard_url)

    assert normalized.startswith("postgresql+psycopg2://")
    parsed = make_url(normalized)
    assert parsed.get_backend_name() == "postgresql"
    assert parsed.get_driver_name() == "psycopg2"
    assert parsed.username == "neon_user"
    assert parsed.password == "secret_pwd"
    assert parsed.host == "ep-cool-123.ap-southeast-1.aws.neon.tech"
    assert parsed.port == 5432
    assert parsed.database == "neondb"


def test_url_query_parameters_preserved():
    sample_url = (
        "postgresql://user:pass@ep-pooler.aws.neon.tech:5432/neondb"
        "?sslmode=require&channel_binding=prefer"
    )
    normalized = _database_url(sample_url)
    assert normalized == (
        "postgresql+psycopg2://user:pass@ep-pooler.aws.neon.tech:5432/neondb"
        "?sslmode=require&channel_binding=prefer"
    )

    parsed = make_url(normalized)
    assert parsed.query["sslmode"] == "require"
    assert parsed.query["channel_binding"] == "prefer"


def test_postgres_legacy_url_with_query_params_preserved():
    sample_url = (
        "postgres://user:pass@ep-pooler.aws.neon.tech:5432/neondb"
        "?sslmode=require"
    )
    normalized = _database_url(sample_url)
    assert normalized == (
        "postgresql+psycopg2://user:pass@ep-pooler.aws.neon.tech:5432/neondb"
        "?sslmode=require"
    )

    parsed = make_url(normalized)
    assert parsed.get_backend_name() == "postgresql"
    assert parsed.get_driver_name() == "psycopg2"
    assert parsed.query["sslmode"] == "require"


def test_already_configured_psycopg2_url_unchanged():
    url = "postgresql+psycopg2://user:pass@host:5432/dbname?sslmode=require"
    assert _database_url(url) == url


def test_database_url_from_environment(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgres://env_user:env_pass@host.region.neon.tech/envdb?sslmode=require",
    )
    normalized = _database_url()
    assert normalized == (
        "postgresql+psycopg2://env_user:env_pass@host.region.neon.tech/envdb?sslmode=require"
    )

