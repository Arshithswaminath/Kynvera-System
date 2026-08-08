"""Tests for startup secret / default-admin bootstrap guards."""
import os

import pytest

from common.bootstrap_security import (
    assert_secure_app_secrets,
    resolve_bootstrap_admin_password,
)


def test_resolve_bootstrap_admin_password_uses_env(monkeypatch):
    monkeypatch.setenv('DEFAULT_ADMIN_PASSWORD', 'EnvPass123!')
    password, generated = resolve_bootstrap_admin_password('development')
    assert password == 'EnvPass123!'
    assert generated is False


def test_resolve_bootstrap_admin_password_refuses_production_without_env(monkeypatch):
    monkeypatch.delenv('DEFAULT_ADMIN_PASSWORD', raising=False)
    monkeypatch.delenv('RENDER', raising=False)
    with pytest.raises(RuntimeError, match='DEFAULT_ADMIN_PASSWORD'):
        resolve_bootstrap_admin_password('production')


def test_resolve_bootstrap_admin_password_refuses_render_without_env(monkeypatch):
    monkeypatch.delenv('DEFAULT_ADMIN_PASSWORD', raising=False)
    monkeypatch.setenv('RENDER', 'true')
    with pytest.raises(RuntimeError, match='DEFAULT_ADMIN_PASSWORD'):
        resolve_bootstrap_admin_password('development')


def test_resolve_bootstrap_admin_password_generates_in_dev(monkeypatch):
    monkeypatch.delenv('DEFAULT_ADMIN_PASSWORD', raising=False)
    password, generated = resolve_bootstrap_admin_password('development')
    assert generated is True
    assert len(password) >= 16


def test_assert_secure_app_secrets_fails_closed_in_production():
    with pytest.raises(RuntimeError, match='JWT_SECRET_KEY'):
        assert_secure_app_secrets(
            'change-me-in-production',
            'change-me-jwt-secret',
            'production',
        )


def test_assert_secure_app_secrets_allows_explicit_values_in_production():
    assert_secure_app_secrets(
        'prod-secret-value-not-default',
        'prod-jwt-secret-value-not-default',
        'production',
    )


def test_assert_secure_app_secrets_warns_but_allows_in_dev(caplog):
    assert_secure_app_secrets(
        'change-me-in-production',
        'change-me-jwt-secret',
        'development',
    )
    assert any('insecure default' in r.message.lower() for r in caplog.records)
