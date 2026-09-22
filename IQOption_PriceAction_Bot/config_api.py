# -*- coding: utf-8 -*-
"""
Configuração de Chaves de API da Binance
NUNCA compartilhe este arquivo ou faça commit em repositórios públicos!
"""

# ===== BINANCE TESTNET (Conta Demo) =====
# Obtenha em: https://testnet.binance.vision/
TESTNET_API_KEY = "cole_sua_testnet_api_key_aqui"
TESTNET_SECRET_KEY = "cole_sua_testnet_secret_key_aqui"

# ===== BINANCE MAINNET (Conta Real) =====
# CUIDADO! Use apenas se souber o que está fazendo
# Obtenha em: https://www.binance.com/pt-BR/my/settings/api-management
MAINNET_API_KEY = "cole_sua_mainnet_api_key_aqui"
MAINNET_SECRET_KEY = "cole_sua_mainnet_secret_key_aqui"

# ===== COMO USAR =====
# 1. Preencha as chaves acima
# 2. No arquivo bot_binance.py, importe este arquivo:
#
#    from config_api import TESTNET_API_KEY, TESTNET_SECRET_KEY
#    
#    self.api_key = TESTNET_API_KEY
#    self.api_secret = TESTNET_SECRET_KEY
#
# 3. Adicione 'config_api.py' ao .gitignore para não compartilhar suas chaves

# ===== INSTRUÇÕES PARA OBTER CHAVES =====

"""
TESTNET (Recomendado para testes):
1. Acesse: https://testnet.binance.vision/
2. Clique em "Generate HMAC_SHA256 Key"
3. Copie a API Key e Secret Key geradas
4. Cole acima nas variáveis TESTNET_*
5. No site do Testnet, você pode gerar fundos virtuais ilimitados

MAINNET (Conta Real - USE COM CUIDADO):
1. Acesse: https://www.binance.com/pt-BR/my/settings/api-management
2. Clique em "Create API"
3. Complete a autenticação de segurança
4. Configure as permissões:
   ✅ Enable Spot & Margin Trading
   ✅ Enable Reading
   ❌ NUNCA ative "Enable Withdrawals" (saques)
5. Configure restrição por IP para maior segurança
6. Copie a API Key e Secret Key
7. Cole acima nas variáveis MAINNET_*

SEGURANÇA:
- NUNCA compartilhe suas chaves
- NUNCA faça commit deste arquivo em repositórios públicos
- Use restrição por IP sempre que possível
- Revogue chaves antigas se criar novas
- Monitore o uso das chaves regularmente
"""
