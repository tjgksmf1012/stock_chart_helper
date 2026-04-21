from __future__ import annotations

import ssl

from app.core.database import normalize_database_url


def test_normalize_database_url_strips_asyncpg_ssl_query_params():
    url, connect_args = normalize_database_url(
        "postgresql+asyncpg://user:pass@example.com/dbname?sslmode=require&channel_binding=require"
    )

    assert "sslmode" not in url
    assert "channel_binding" not in url
    assert connect_args["ssl"].verify_mode == ssl.CERT_NONE
    assert connect_args["ssl"].check_hostname is False


def test_normalize_database_url_leaves_non_asyncpg_url_unchanged():
    url, connect_args = normalize_database_url(
        "postgresql://user:pass@example.com/dbname?sslmode=require"
    )

    assert url == "postgresql://user:pass@example.com/dbname?sslmode=require"
    assert connect_args == {}
