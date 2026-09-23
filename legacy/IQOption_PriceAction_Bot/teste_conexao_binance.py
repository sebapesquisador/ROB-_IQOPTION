# -*- coding: utf-8 -*-
"""
Teste de Conexão com Binance
Use este script para verificar se suas chaves de API estão funcionando
"""

from binance.client import Client
import sys

def testar_conexao():
    """Testa a conexão com a Binance"""
    
    print("=" * 60)
    print("TESTE DE CONEXÃO COM BINANCE")
    print("=" * 60)
    print()
    
    # Solicita as chaves
    print("Você está testando:")
    print("1. Testnet (conta demo)")
    print("2. Mainnet (conta real)")
    escolha = input("\nEscolha (1 ou 2): ").strip()
    
    usar_testnet = (escolha == "1")
    
    print()
    api_key = input("Cole sua API Key: ").strip()
    api_secret = input("Cole sua Secret Key: ").strip()
    
    print()
    print("-" * 60)
    
    try:
        # Cria cliente
        if usar_testnet:
            print("🧪 Conectando ao Testnet...")
            client = Client(api_key, api_secret, testnet=True)
        else:
            print("⚠️  Conectando ao Mainnet (REAL)...")
            client = Client(api_key, api_secret)
        
        # Testa status do sistema
        status = client.get_system_status()
        print(f"✅ Status do sistema: {status['msg']}")
        
        # Testa informações da conta
        print("\n📊 Obtendo informações da conta...")
        account = client.get_account()
        
        print("✅ Conta acessada com sucesso!")
        print("\n💰 SALDOS:")
        
        tem_saldo = False
        for balance in account['balances']:
            free = float(balance['free'])
            locked = float(balance['locked'])
            if free > 0 or locked > 0:
                tem_saldo = True
                print(f"   {balance['asset']}: {free:.8f} (Bloqueado: {locked:.8f})")
        
        if not tem_saldo:
            print("   Nenhum saldo encontrado")
            if usar_testnet:
                print("\n💡 DICA: No Testnet, você precisa 'gerar' fundos virtuais")
                print("   Acesse: https://testnet.binance.vision/")
                print("   E use a opção de adicionar fundos de teste")
        
        # Testa obtenção de preço
        print("\n📈 Testando obtenção de preços...")
        ticker = client.get_symbol_ticker(symbol="BTCUSDT")
        print(f"✅ BTC/USDT: ${ticker['price']}")
        
        # Testa obtenção de candlesticks
        print("\n📊 Testando obtenção de dados históricos...")
        klines = client.get_klines(symbol="BTCUSDT", interval="5m", limit=10)
        print(f"✅ Recebidos {len(klines)} candles de 5 minutos")
        
        print("\n" + "=" * 60)
        print("✅ TODOS OS TESTES PASSARAM!")
        print("=" * 60)
        print("\n✨ Suas chaves de API estão funcionando corretamente!")
        print("   Você pode usar o bot agora.")
        
        if not usar_testnet:
            print("\n⚠️  ATENÇÃO: Você está usando a conta REAL!")
            print("   Certifique-se de configurar limites de segurança.")
        
        return True
        
    except Exception as e:
        print("\n" + "=" * 60)
        print("❌ ERRO NO TESTE")
        print("=" * 60)
        print(f"\nErro: {e}")
        print("\n🔍 Possíveis causas:")
        print("   1. API Key ou Secret Key incorretas")
        print("   2. Você escolheu Testnet mas usou chaves do Mainnet (ou vice-versa)")
        print("   3. Suas chaves não têm as permissões necessárias")
        print("   4. Problema de conexão com a internet")
        
        print("\n💡 Soluções:")
        print("   - Verifique se copiou as chaves COMPLETAS (sem espaços)")
        print("   - Confirme se escolheu Testnet/Mainnet correto")
        print("   - No Mainnet: verifique as permissões da API Key")
        print("   - Tente gerar novas chaves")
        
        if usar_testnet:
            print("\n🔗 Gerar novas chaves Testnet: https://testnet.binance.vision/")
        else:
            print("\n🔗 Gerenciar chaves Mainnet: https://www.binance.com/pt-BR/my/settings/api-management")
        
        return False

if __name__ == "__main__":
    testar_conexao()
    print("\nPressione Enter para sair...")
    input()
