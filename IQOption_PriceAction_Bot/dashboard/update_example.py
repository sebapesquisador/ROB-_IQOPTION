#!/usr/bin/env python3
# Exemplo de como atualizar o painel (simula o bot)
import requests
import time

URL = "http://127.0.0.1:5001/update"

def send_update():
    payload = {
        "ativo": "EURUSD",
        "timeframe": "1m",
        "estrategia": "3",
        "lucro_diario": 12.5,
        "lucro_total": 150.75,
        "total_trades": 25,
        "wins": 15
    }
    try:
        r = requests.post(URL, json=payload, timeout=5)
        print(r.status_code, r.text)
    except Exception as e:
        print('Erro:', e)

if __name__ == '__main__':
    send_update()
