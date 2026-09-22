#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para testar o status do Testnet da Binance
"""

import requests
import time
from datetime import datetime

def testar_testnet():
    """Testa se o Testnet da Binance está respondendo"""
    
    urls = {
        "Testnet API": "https://testnet.binance.vision/api/v3/ping",
        "Testnet Site": "https://testnet.binance.vision/",
        "Binance API (Produção)": "https://api.binance.com/api/v3/ping"
    }
    
    print("=" * 60)
    print(f"🔍 TESTANDO CONECTIVIDADE - {datetime.now().strftime('%H:%M:%S')}")
    print("=" * 60)
    
    for nome, url in urls.items():
        try:
            print(f"\n📡 Testando {nome}...")
            print(f"   URL: {url}")
            
            inicio = time.time()
            response = requests.get(url, timeout=10)
            tempo = (time.time() - inicio) * 1000
            
            if response.status_code == 200:
                print(f"   ✅ ONLINE - Status: {response.status_code}")
                print(f"   ⏱️  Latência: {tempo:.0f}ms")
            else:
                print(f"   ⚠️  PROBLEMA - Status: {response.status_code}")
                
        except requests.exceptions.Timeout:
            print(f"   ❌ TIMEOUT - Servidor não respondeu em 10s")
        except requests.exceptions.ConnectionError:
            print(f"   ❌ ERRO DE CONEXÃO - Servidor inacessível")
        except Exception as e:
            print(f"   ❌ ERRO: {str(e)[:100]}")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    testar_testnet()
    
    print("\n💡 DICAS:")
    print("   • Se o Testnet estiver offline, aguarde alguns minutos")
    print("   • Se a API de Produção estiver online, o problema é só no Testnet")
    print("   • Você pode usar a API real (com cuidado!) mudando usar_testnet=False")
    print("\n🔄 Pressione Ctrl+C para sair ou aguarde...")
    
    # Teste contínuo a cada 30 segundos
    try:
        while True:
            time.sleep(30)
            print("\n")
            testar_testnet()
    except KeyboardInterrupt:
        print("\n\n👋 Teste finalizado!")
