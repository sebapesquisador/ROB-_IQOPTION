"""Testes da API e do painel de controle."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from trading_bot.api import server as srv


@pytest.fixture
def client(tmp_path, monkeypatch):
    from trading_bot.core.config import (
        AccountMode, Broker as B, RiskConfig, SessionConfig, Settings, StrategyConfig,
    )

    settings = Settings(
        broker=B.PAPER, account_mode=AccountMode.DEMO, dry_run=True,
        symbol="EURUSD", timeframe_minutes=5, expiration_minutes=5,
        poll_interval_seconds=1, api_token=None,
        database_url=f"sqlite:///{tmp_path/'api.db'}",
        strategy=StrategyConfig(name="confluence", min_confidence=0.5),
        risk=RiskConfig(sizing_mode="fixed", fixed_stake=10.0),
        session=SessionConfig(start_time="00:00", end_time="23:59",
                              trade_on_weekends=True,
                              weekday_whitelist=[0, 1, 2, 3, 4, 5, 6]),
    )
    monkeypatch.setattr("trading_bot.core.config.get_settings", lambda reload=False: settings)
    monkeypatch.setattr(srv, "get_settings", lambda reload=False: settings)

    with TestClient(srv.app) as c:
        yield c


class TestBasics:
    def test_health(self, client):
        assert client.get("/health").status_code == 200

    def test_dashboard_renders(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "Trading Bot" in r.text

    def test_static_assets(self, client):
        assert client.get("/static/style.css").status_code == 200
        assert client.get("/static/app.js").status_code == 200


class TestStatusAndConfig:
    def test_status_shape(self, client):
        d = client.get("/api/status").json()
        for k in ("state", "broker", "strategy", "symbol", "dry_run"):
            assert k in d

    def test_config_lists_strategies(self, client):
        d = client.get("/api/config").json()
        assert len(d["strategies_available"]) >= 5

    def test_config_never_leaks_secrets(self, client):
        """Nenhum endpoint pode devolver senha ou chave de API."""
        body = client.get("/api/config").text.lower()
        for leak in ("iq_password", "binance_api_secret", "password"):
            assert leak not in body

    def test_update_config(self, client):
        r = client.patch("/api/config", json={"min_confidence": 0.75})
        assert r.status_code == 200
        assert r.json()["changed"]["min_confidence"] == 0.75

    def test_invalid_strategy_rejected(self, client):
        assert client.patch("/api/config", json={"strategy": "inexistente"}).status_code == 400

    def test_out_of_range_values_rejected(self, client):
        assert client.patch("/api/config", json={"percent_stake": 99.0}).status_code == 422
        assert client.patch("/api/config", json={"min_confidence": 5.0}).status_code == 422


class TestControl:
    def test_start_pause_resume_stop(self, client):
        assert client.post("/api/control/start").json()["state"] == "running"
        assert client.post("/api/control/pause").json()["state"] == "paused"
        assert client.post("/api/control/resume").json()["state"] == "running"
        assert client.post("/api/control/stop").json()["state"] == "stopped"

    def test_structural_change_blocked_while_running(self, client):
        client.post("/api/control/start")
        r = client.patch("/api/config", json={"symbol": "GBPUSD"})
        client.post("/api/control/stop")
        assert r.status_code == 409

    def test_structural_change_allowed_when_stopped(self, client):
        r = client.patch("/api/config", json={"symbol": "GBPUSD"})
        assert r.status_code == 200
        assert r.json()["changed"]["symbol"] == "GBPUSD"


class TestData:
    def test_trades_empty_initially(self, client):
        assert client.get("/api/trades").json() == []

    def test_performance_shape(self, client):
        d = client.get("/api/performance").json()
        for k in ("daily", "by_strategy", "equity_curve"):
            assert k in d

    def test_candles(self, client):
        d = client.get("/api/candles?limit=50").json()
        assert len(d["candles"]) <= 50
        assert "rsi" in d["candles"][-1]

    def test_backtest(self, client):
        r = client.post("/api/backtest", json={
            "candles": 400, "payout": 0.85, "strategies": ["rsi_reversal"],
        })
        assert r.status_code == 200
        d = r.json()
        assert d["breakeven_win_rate"] == 54.05
        assert d["results"][0]["strategy"] == "rsi_reversal"


class TestAuth:
    def test_token_protects_writes(self, tmp_path, monkeypatch):
        from trading_bot.core.config import Broker as B, Settings, StrategyConfig

        settings = Settings(
            broker=B.PAPER, dry_run=True, api_token="segredo123",
            database_url=f"sqlite:///{tmp_path/'auth.db'}",
            strategy=StrategyConfig(name="confluence"),
        )
        monkeypatch.setattr(srv, "get_settings", lambda reload=False: settings)

        with TestClient(srv.app) as c:
            assert c.get("/api/status").status_code == 200          # leitura livre
            assert c.post("/api/control/start").status_code == 401   # escrita bloqueada
            ok = c.post("/api/control/start", headers={"X-API-Token": "segredo123"})
            assert ok.status_code == 200
            c.post("/api/control/stop", headers={"X-API-Token": "segredo123"})
