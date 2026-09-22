# -*- coding: utf-8 -*-
"""
Script de teste para verificar ativos disponíveis na IQ Option
"""

from iqoptionapi.stable_api import IQ_Option
import time

# Credenciais
email = "seba.sebastian7@hotmail.com"
senha = "Havila070766"

print("=" * 60)
print("TESTANDO CONEXÃO E ATIVOS DISPONÍVEIS")
print("=" * 60)

# Conecta
api = IQ_Option(email, senha)
check, reason = api.connect()

if check:
    print("✅ Conectado com sucesso!")
    
    # Muda para demo
    api.change_balance("PRACTICE")
    saldo = api.get_balance()
    print(f"💰 Saldo DEMO: ${saldo:.2f}")
    
    print("\n" + "=" * 60)
    print("TESTANDO DIFERENTES ATIVOS E MÉTODOS")
    print("=" * 60)
    
    # Lista de ativos para testar
    ativos = [
        "EURUSD",
        "EURUSD-OTC",
        "GBPUSD-OTC",
        "USDJPY-OTC"
    ]
    
    for ativo in ativos:
        print(f"\n📊 Testando: {ativo}")
        print("-" * 40)
        
        # Testa Digital Options
        print("   [1] Tentando Digital Options...", end=" ", flush=True)
        try:
            check, order_id = api.buy_digital_spot(ativo, 1, "call", 1)
            print(f"Resposta recebida!")
            if check and order_id and order_id > 0:
                print(f"   ✅ DIGITAL OPTIONS FUNCIONA! ID: {order_id}")
            else:
                print(f"   ❌ Digital Options falhou (check={check}, id={order_id})")
        except Exception as e:
            print(f"\n   ❌ Erro: {e}")
        
        time.sleep(2)
        
        # Testa Binary Options
        print("   [2] Tentando Binary Options...", end=" ", flush=True)
        try:
            check, order_id = api.buy(1, ativo, "call", 1)
            print(f"Resposta recebida!")
            if check and order_id and order_id > 0:
                print(f"   ✅ BINARY OPTIONS FUNCIONA! ID: {order_id}")
            else:
                print(f"   ❌ Binary Options falhou (check={check}, id={order_id})")
        except Exception as e:
            print(f"\n   ❌ Erro: {e}")
        
        time.sleep(2)
    
    print("\n" + "=" * 60)
    print("VERIFICANDO ATIVOS ABERTOS")
    print("=" * 60)
    
    try:
        all_assets = api.get_all_open_time()
        
        print("\n🔵 BINARY OPTIONS disponíveis:")
        if 'binary' in all_assets:
            count = 0
            for asset in all_assets['binary']:
                if 'OTC' in asset or 'USD' in asset:
                    print(f"   - {asset}")
                    count += 1
                    if count >= 10:
                        break
        
        print("\n🟢 DIGITAL OPTIONS disponíveis:")
        if 'digital' in all_assets:
            count = 0
            for asset in all_assets['digital']:
                if 'OTC' in asset or 'USD' in asset:
                    print(f"   - {asset}")
                    count += 1
                    if count >= 10:
                        break
    except Exception as e:
        print(f"❌ Erro ao buscar ativos: {e}")
    
    api.close()
    print("\n✅ Teste concluído!")
    
else:
    print(f"❌ Falha na conexão: {reason}")

print("=" * 60)
