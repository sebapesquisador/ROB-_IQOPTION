#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Painel web para mostrar status do bot IQ Option

Endpoints:
 - GET  /           -> Dashboard HTML
 - GET  /state      -> JSON com estado atual
 - POST /update     -> Atualiza o estado (json body)
 - POST /reset_daily -> Zera lucro diário
 - POST /reset_total -> Zera lucro total
 - POST /add_trade  -> Adiciona trade ao histórico
 - GET  /history    -> Retorna histórico de trades

Proteção opcional: variável de ambiente DASHBOARD_API_KEY
"""

import os
import json
from flask import Flask, render_template, jsonify, request, abort
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "state.json"
HISTORY_FILE = BASE_DIR / "history.json"

app = Flask(__name__, static_folder=str(BASE_DIR / "static"), template_folder=str(BASE_DIR / "templates"))

API_KEY = os.environ.get("DASHBOARD_API_KEY")

def _load_state():
    if not STATE_FILE.exists():
        _save_state({
            "ativo": "EURUSD",
            "timeframe": "1m",
            "estrategia": "3",
            "lucro_diario": 0.0,
            "lucro_total": 0.0,
            "winrate": 0.0,
            "total_trades": 0,
            "wins": 0,
            "updated_at": datetime.utcnow().isoformat() + "Z"
        })
    with STATE_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)

def _save_state(state: dict):
    state["updated_at"] = datetime.utcnow().isoformat() + "Z"
    with STATE_FILE.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def _load_history():
    if not HISTORY_FILE.exists():
        return []
    with HISTORY_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)

def _save_history(history: list):
    # Mantém apenas últimos 100 trades
    history = history[-100:]
    with HISTORY_FILE.open("w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def _require_key():
    if API_KEY is None:
        return True
    key = request.headers.get("X-API-KEY") or request.args.get("api_key")
    return key == API_KEY

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/state")
def get_state():
    state = _load_state()
    return jsonify(state)

@app.route("/history")
def get_history():
    history = _load_history()
    return jsonify(history)

@app.route("/update", methods=["POST"])
def update_state():
    if not _require_key():
        abort(401)
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "invalid json"}), 400

    state = _load_state()
    # Merge known fields only
    allowed = ["ativo", "timeframe", "estrategia", "lucro_diario", "lucro_total", "winrate", "total_trades", "wins"]
    for k in allowed:
        if k in data:
            state[k] = data[k]

    # Recalculate winrate if possible
    try:
        if state.get("total_trades"):
            state["winrate"] = round((state.get("wins", 0) / max(1, state.get("total_trades"))) * 100, 2)
    except Exception:
        pass

    _save_state(state)
    return jsonify(state)

@app.route("/add_trade", methods=["POST"])
def add_trade():
    if not _require_key():
        abort(401)
    try:
        trade = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "invalid json"}), 400
    
    history = _load_history()
    history.append(trade)
    _save_history(history)
    
    return jsonify({"status": "ok", "total": len(history)})

@app.route("/reset_daily", methods=["POST"])
def reset_daily():
    if not _require_key():
        abort(401)
    state = _load_state()
    state["lucro_diario"] = 0.0
    _save_state(state)
    return jsonify(state)

@app.route("/reset_total", methods=["POST"])
def reset_total():
    if not _require_key():
        abort(401)
    state = _load_state()
    state["lucro_total"] = 0.0
    _save_state(state)
    return jsonify(state)

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    # Cria pasta se necessário
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    # Ensure state exists
    _load_state()
    _load_history()
    print("=" * 60)
    print("🚀 PAINEL IQ OPTION INICIADO")
    print("=" * 60)
    print(f"📊 Dashboard: http://127.0.0.1:5001")
    print(f"🔌 API Estado: http://127.0.0.1:5001/state")
    print(f"📈 API Histórico: http://127.0.0.1:5001/history")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5001)
