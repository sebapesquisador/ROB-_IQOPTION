# -*- coding: utf-8 -*-
"""
EA PRICE ACTION v2.0 - Adaptado para Binance
Bot de Trading Automático com 11 Estratégias
"""

import time
import json
import logging
from datetime import datetime, timedelta
from binance.client import Client
from binance.enums import *
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import os
from decimal import Decimal, ROUND_DOWN

# =============================================================================
# CONFIGURAÇÕES DE LOG
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_binance.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# =============================================================================
# CLASSE PRINCIPAL DO BOT
# =============================================================================
class BinancePriceActionBot:
    """Bot de trading para Binance com 11 estratégias de Price Action"""
    
    def __init__(self):
        """Inicializa o bot"""
        # ===== CREDENCIAIS BINANCE =====
        # IMPORTANTE: Nunca compartilhe suas chaves de API!
        self.api_key = ""  # REMOVIDO - use .env  # ← COLOQUE SUA API KEY AQUI
        self.api_secret = ""  # REMOVIDO - use .env  # ← COLOQUE SUA SECRET KEY AQUI
        
        # ===== CONFIGURAÇÕES GERAIS =====
        self.estrategia_escolhida = 4  # 1 a 11
        self.par_negociacao = "ETHUSDT"  # Par de negociação (ex: BTCUSDT, ETHUSDT, BNBUSDT)
        self.timeframe = "1m"  # Timeframe: 1m, 3m, 5m, 15m, 30m, 1h, 4h, 1d
        self.valor_operacao_usdt = 15.0  # Valor em USDT por operação (mínimo geralmente 10 USDT)
        self.usar_testnet = True  # True = Testnet (demo) | False = Mainnet (real)
        
        # ===== PARÂMETROS RSI (Estratégias 1, 2, 3) =====
        self.rsi_periodo = 14
        self.rsi_sobrevenda = 30.0
        self.rsi_sobrecompra = 70.0
        self.rsi_saida_meio = 50.0
        
        # ===== PARÂMETROS ESTRATÉGIA 4 =====
        self.ma21_periodo_est4 = 21
        self.rsi_periodo_est4 = 14
        self.stop_loss_percent_est4 = 2.0  # 2% de stop loss
        self.take_profit_percent_est4 = 1.0  # 1% de take profit
        
        # ===== PARÂMETROS ESTRATÉGIAS 5 e 6 =====
        self.ma21_periodo = 21
        self.ma5_periodo = 5
        self.rsi_periodo_est5 = 14
        self.stop_loss_percent_est5 = 2.0
        self.take_profit_percent_est5 = 1.0
        
        # ===== PARÂMETROS ESTRATÉGIAS 7 e 8 =====
        self.ma21_periodo_est7 = 21
        self.stop_loss_percent_est7 = 2.0
        self.take_profit_percent_est7 = 1.0
        
        self.ma21_periodo_est8 = 21
        self.stop_loss_percent_est8 = 5.0
        self.take_profit_percent_est8 = 10.0
        
        # ===== PARÂMETROS ESTRATÉGIAS 9 e 10 =====
        self.ma21_periodo_est9 = 21
        self.stop_loss_percent_est9 = 2.0
        self.take_profit_percent_est9 = 1.0
        
        self.ma21_periodo_est10 = 21
        self.stop_loss_percent_est10 = 2.0
        self.take_profit_percent_est10 = 1.0
        
        # ===== PARÂMETROS ESTRATÉGIA 11 - BANDAS DE BOLLINGER =====
        self.bb_periodo = 20
        self.bb_desvio = 2.8
        self.stop_loss_percent_est11 = 2.0
        self.take_profit_percent_est11 = 1.0
        
        # ===== METAS =====
        self.meta_diaria = 100.0  # Meta diária em USDT
        self.meta_total = 500.0  # Meta total em USDT
        
        # ===== HORÁRIO DE NEGOCIAÇÃO =====
        self.usar_horario = True
        self.hora_inicio = "00:00"
        self.hora_fim = "23:59"
        
        # ===== TRAILING STOP =====
        self.usar_trailing_stop = False
        self.trailing_distance_percent = 1.0
        self.trailing_step_percent = 0.5
        
        # ===== VARIÁVEIS DE CONTROLE =====
        self.client = None
        self.conectado = False
        self.ea_ativo = True
        self.lucro_total = 0.0
        self.lucro_diario = 0.0
        self.total_trades = 0
        self.trades_vencedores = 0
        self.posicoes_abertas = []
        self.ultimo_candle_entrada = None
        self.ultimo_candle_compra = None
        self.ultimo_candle_venda = None
        self.rsi_anterior = 50.0
        self.aguardando_pullback_compra = False
        self.aguardando_pullback_venda = False
        
        # Info do par de negociação
        self.symbol_info = None
        self.price_precision = 2
        self.qty_precision = 6
        self.min_notional = 10.0
        
    # =========================================================================
    # CONEXÃO COM BINANCE
    # =========================================================================
    
    def conectar(self) -> bool:
        """Conecta à API da Binance"""
        try:
            logger.info("=" * 60)
            logger.info("INICIANDO CONEXÃO COM BINANCE")
            logger.info("=" * 60)
            
            # Verifica se as chaves foram configuradas
            if self.api_key == "SUA_API_KEY_AQUI" or self.api_secret == "SUA_SECRET_KEY_AQUI":
                logger.error("❌ Configure suas chaves de API no código!")
                logger.error("   Edite as variáveis api_key e api_secret")
                return False
            
            # Conecta à Binance Testnet ou Mainnet
            if self.usar_testnet:
                logger.info("🧪 Modo: TESTNET (Conta Demo)")
                # Testnet URLs - com configurações para evitar erro de timestamp
                self.client = Client(
                    self.api_key,
                    self.api_secret,
                    testnet=True
                )
                # Sincroniza o timestamp com o servidor
                self.client.timestamp_offset = self._obter_offset_tempo()
            else:
                logger.warning("⚠️ Modo: MAINNET (Conta REAL)")
                self.client = Client(self.api_key, self.api_secret)
                # Sincroniza o timestamp com o servidor
                self.client.timestamp_offset = self._obter_offset_tempo()
            
            # Testa a conexão
            status = self.client.get_system_status()
            logger.info(f"✅ Status do sistema: {status['msg']}")
            
            # Obtém informações da conta
            account = self.client.get_account()
            
            # Mostra saldo
            logger.info("-" * 60)
            logger.info("💰 SALDOS DISPONÍVEIS:")
            for balance in account['balances']:
                free = float(balance['free'])
                locked = float(balance['locked'])
                if free > 0 or locked > 0:
                    logger.info(f"   {balance['asset']}: {free:.8f} (Locked: {locked:.8f})")
            
            # Obtém informações do par de negociação
            self._obter_info_simbolo()
            
            logger.info("-" * 60)
            logger.info(f"📊 Par de negociação: {self.par_negociacao}")
            logger.info(f"⏱️ Timeframe: {self.timeframe}")
            logger.info(f"💵 Valor por operação: {self.valor_operacao_usdt} USDT")
            logger.info(f"🎯 Estratégia: {self.estrategia_escolhida}")
            logger.info(f"🕒 Horário: {self.hora_inicio} - {self.hora_fim}")
            logger.info("=" * 60)
            
            self.conectado = True
            return True
            
        except Exception as e:
            logger.error(f"❌ Erro ao conectar: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def _obter_offset_tempo(self) -> int:
        """Calcula o offset de tempo entre o servidor e o cliente"""
        try:
            import time
            # Tempo local em milissegundos
            tempo_local = int(time.time() * 1000)
            
            # Tempo do servidor
            tempo_servidor = self.client.get_server_time()['serverTime']
            
            # Calcula o offset
            offset = tempo_servidor - tempo_local
            
            if abs(offset) > 1000:
                logger.info(f"⏰ Sincronizando relógio: offset de {offset}ms")
            
            return offset
        except Exception as e:
            logger.warning(f"⚠️ Não foi possível sincronizar o tempo: {e}")
            return 0
    
    def _obter_info_simbolo(self):
        """Obtém informações sobre o par de negociação"""
        try:
            info = self.client.get_symbol_info(self.par_negociacao)
            self.symbol_info = info
            
            # Extrai precisões
            for filter in info['filters']:
                if filter['filterType'] == 'PRICE_FILTER':
                    tick_size = filter['tickSize']
                    self.price_precision = len(tick_size.rstrip('0').split('.')[-1])
                elif filter['filterType'] == 'LOT_SIZE':
                    step_size = filter['stepSize']
                    self.qty_precision = len(step_size.rstrip('0').split('.')[-1])
                elif filter['filterType'] == 'MIN_NOTIONAL':
                    self.min_notional = float(filter['minNotional'])
            
            logger.info(f"   Precisão de preço: {self.price_precision} casas decimais")
            logger.info(f"   Precisão de quantidade: {self.qty_precision} casas decimais")
            logger.info(f"   Valor mínimo de negociação: {self.min_notional} USDT")
            
        except Exception as e:
            logger.error(f"Erro ao obter informações do símbolo: {e}")
    
    def desconectar(self):
        """Desconecta da API"""
        try:
            logger.info("🔌 Desconectado da Binance")
            self.conectado = False
        except Exception as e:
            logger.warning(f"⚠️ Erro ao desconectar: {e}")
    
    # =========================================================================
    # OBTENÇÃO DE DADOS
    # =========================================================================
    
    def obter_candles(self, quantidade: int = 100) -> Optional[pd.DataFrame]:
        """Obtém histórico de candles da Binance"""
        try:
            # Busca klines (candles) da Binance
            klines = self.client.get_klines(
                symbol=self.par_negociacao,
                interval=self.timeframe,
                limit=quantidade
            )
            
            # Converte para DataFrame
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                'taker_buy_quote', 'ignore'
            ])
            
            # Converte tipos
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['open'] = df['open'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            df['close'] = df['close'].astype(float)
            df['volume'] = df['volume'].astype(float)
            
            # Renomeia para compatibilidade
            df = df.rename(columns={
                'timestamp': 'time',
                'open': 'open',
                'high': 'max',
                'low': 'min',
                'close': 'close'
            })
            
            df = df[['time', 'open', 'max', 'min', 'close', 'volume']]
            
            return df
            
        except Exception as e:
            logger.error(f"Erro ao obter candles: {e}")
            return None
    
    # =========================================================================
    # INDICADORES TÉCNICOS
    # =========================================================================
    
    def calcular_rsi(self, df: pd.DataFrame, periodo: int = 14) -> float:
        """Calcula o RSI (Relative Strength Index)"""
        try:
            closes = df['close'].values
            
            if len(closes) < periodo + 1:
                return 50.0
            
            deltas = np.diff(closes)
            ganhos = np.where(deltas > 0, deltas, 0)
            perdas = np.where(deltas < 0, -deltas, 0)
            
            media_ganhos = np.mean(ganhos[-periodo:])
            media_perdas = np.mean(perdas[-periodo:])
            
            if media_perdas == 0:
                return 100.0
            
            rs = media_ganhos / media_perdas
            rsi = 100 - (100 / (1 + rs))
            
            return rsi
            
        except Exception as e:
            logger.error(f"Erro ao calcular RSI: {e}")
            return 50.0
    
    def calcular_ma(self, df: pd.DataFrame, periodo: int = 21) -> float:
        """Calcula a Média Móvel Simples"""
        try:
            closes = df['close'].values
            if len(closes) < periodo:
                return closes[-1]
            
            ma = np.mean(closes[-periodo:])
            return ma
            
        except Exception as e:
            logger.error(f"Erro ao calcular MA: {e}")
            return df['close'].iloc[-1]
    
    def calcular_bollinger_bands(self, df: pd.DataFrame, periodo: int = 20, desvio: float = 2.0) -> Tuple[float, float, float]:
        """Calcula as Bandas de Bollinger (superior, média, inferior)"""
        try:
            closes = df['close'].values
            if len(closes) < periodo:
                preco_atual = closes[-1]
                return preco_atual, preco_atual, preco_atual
            
            ma = np.mean(closes[-periodo:])
            std = np.std(closes[-periodo:])
            
            upper_band = ma + (desvio * std)
            lower_band = ma - (desvio * std)
            
            return upper_band, ma, lower_band
            
        except Exception as e:
            logger.error(f"Erro ao calcular Bollinger Bands: {e}")
            preco_atual = df['close'].iloc[-1]
            return preco_atual, preco_atual, preco_atual
    
    # =========================================================================
    # EXECUÇÃO DE ORDENS
    # =========================================================================
    
    def formatar_quantidade(self, quantidade: float) -> str:
        """Formata a quantidade com a precisão correta"""
        qty_str = f"{quantidade:.{self.qty_precision}f}"
        return qty_str
    
    def formatar_preco(self, preco: float) -> str:
        """Formata o preço com a precisão correta"""
        price_str = f"{preco:.{self.price_precision}f}"
        return price_str
    
    def calcular_quantidade(self, preco_atual: float) -> float:
        """Calcula a quantidade a comprar baseado no valor em USDT"""
        quantidade = self.valor_operacao_usdt / preco_atual
        
        # Arredonda para baixo com a precisão correta
        quantidade_str = self.formatar_quantidade(quantidade)
        quantidade_formatada = float(quantidade_str)
        
        return quantidade_formatada
    
    def abrir_posicao_compra(self, preco_entrada: float, stop_loss_percent: float = None, take_profit_percent: float = None) -> bool:
        """Abre uma posição de COMPRA (LONG)"""
        try:
            quantidade = self.calcular_quantidade(preco_entrada)
            
            logger.info(f"📈 Abrindo posição COMPRA")
            logger.info(f"   Preço: {preco_entrada:.8f}")
            logger.info(f"   Quantidade: {quantidade:.8f}")
            logger.info(f"   Valor: {self.valor_operacao_usdt} USDT")
            
            # Cria ordem MARKET de compra
            order = self.client.create_order(
                symbol=self.par_negociacao,
                side=SIDE_BUY,
                type=ORDER_TYPE_MARKET,
                quantity=self.formatar_quantidade(quantidade)
            )
            
            logger.info(f"✅ Ordem executada: {order['orderId']}")
            
            # Registra a posição
            posicao = {
                'tipo': 'COMPRA',
                'preco_entrada': preco_entrada,
                'quantidade': quantidade,
                'timestamp': datetime.now(),
                'order_id': order['orderId'],
                'stop_loss': preco_entrada * (1 - stop_loss_percent / 100) if stop_loss_percent else None,
                'take_profit': preco_entrada * (1 + take_profit_percent / 100) if take_profit_percent else None
            }
            
            self.posicoes_abertas.append(posicao)
            return True
            
        except Exception as e:
            logger.error(f"❌ Erro ao abrir posição de compra: {e}")
            return False
    
    def abrir_posicao_venda(self, preco_entrada: float, stop_loss_percent: float = None, take_profit_percent: float = None) -> bool:
        """Abre uma posição de VENDA (SHORT) - na Binance Spot, isso vende o ativo"""
        try:
            # Na Binance Spot, só podemos vender se tivermos o ativo
            # Para fazer SHORT real, seria necessário usar Binance Futures
            
            # Aqui vamos apenas fechar posições de compra anteriores
            logger.info(f"📉 Sinal de VENDA detectado")
            
            if len(self.posicoes_abertas) > 0:
                return self.fechar_todas_posicoes(preco_entrada)
            else:
                logger.info("   Nenhuma posição aberta para fechar")
                return False
            
        except Exception as e:
            logger.error(f"❌ Erro ao processar venda: {e}")
            return False
    
    def fechar_posicao(self, posicao: dict, preco_saida: float) -> bool:
        """Fecha uma posição específica"""
        try:
            logger.info(f"🔄 Fechando posição {posicao['tipo']}")
            
            # Cria ordem MARKET de venda
            order = self.client.create_order(
                symbol=self.par_negociacao,
                side=SIDE_SELL,
                type=ORDER_TYPE_MARKET,
                quantity=self.formatar_quantidade(posicao['quantidade'])
            )
            
            # Calcula lucro/prejuízo
            lucro = (preco_saida - posicao['preco_entrada']) * posicao['quantidade']
            self.lucro_total += lucro
            self.lucro_diario += lucro
            self.total_trades += 1
            
            if lucro > 0:
                self.trades_vencedores += 1
                logger.info(f"✅ Lucro: {lucro:.2f} USDT")
            else:
                logger.info(f"❌ Prejuízo: {lucro:.2f} USDT")
            
            # Remove da lista de posições
            self.posicoes_abertas.remove(posicao)
            
            self._mostrar_estatisticas()
            return True
            
        except Exception as e:
            logger.error(f"❌ Erro ao fechar posição: {e}")
            return False
    
    def fechar_todas_posicoes(self, preco_saida: float) -> bool:
        """Fecha todas as posições abertas"""
        try:
            if len(self.posicoes_abertas) == 0:
                return True
            
            posicoes_para_fechar = self.posicoes_abertas.copy()
            
            for posicao in posicoes_para_fechar:
                self.fechar_posicao(posicao, preco_saida)
            
            return True
            
        except Exception as e:
            logger.error(f"Erro ao fechar todas as posições: {e}")
            return False
    
    def verificar_stop_loss_take_profit(self, preco_atual: float):
        """Verifica se alguma posição atingiu stop loss ou take profit"""
        try:
            posicoes_para_fechar = []
            
            for posicao in self.posicoes_abertas:
                # Verifica Stop Loss
                if posicao['stop_loss'] and preco_atual <= posicao['stop_loss']:
                    logger.info(f"🛑 Stop Loss atingido! Preço: {preco_atual:.8f}")
                    posicoes_para_fechar.append(posicao)
                
                # Verifica Take Profit
                elif posicao['take_profit'] and preco_atual >= posicao['take_profit']:
                    logger.info(f"🎯 Take Profit atingido! Preço: {preco_atual:.8f}")
                    posicoes_para_fechar.append(posicao)
            
            # Fecha as posições que atingiram SL ou TP
            for posicao in posicoes_para_fechar:
                self.fechar_posicao(posicao, preco_atual)
                
        except Exception as e:
            logger.error(f"Erro ao verificar SL/TP: {e}")
    
    # =========================================================================
    # ESTRATÉGIAS DE TRADING
    # =========================================================================
    
    def executar_estrategia_1(self, df: pd.DataFrame):
        """Estratégia 1: RSI Reversão (uma posição por vez)"""
        try:
            rsi = self.calcular_rsi(df, self.rsi_periodo)
            preco_atual = df['close'].iloc[-1]
            
            logger.info(f"📊 Análise: RSI={rsi:.2f} | Sobrevenda<{self.rsi_sobrevenda} | Sobrecompra>{self.rsi_sobrecompra}")
            
            # Sinal de COMPRA
            if rsi < self.rsi_sobrevenda and len(self.posicoes_abertas) == 0:
                logger.info(f"🟢 Sinal COMPRA - RSI em sobrevenda ({rsi:.2f})")
                self.abrir_posicao_compra(preco_atual)
            
            # Sinal de VENDA (fecha posições)
            elif rsi > self.rsi_sobrecompra and len(self.posicoes_abertas) > 0:
                logger.info(f"🔴 Sinal VENDA - RSI em sobrecompra ({rsi:.2f})")
                self.fechar_todas_posicoes(preco_atual)
                
        except Exception as e:
            logger.error(f"Erro na Estratégia 1: {e}")
    
    def executar_estrategia_2(self, df: pd.DataFrame):
        """Estratégia 2: RSI Acumulação com Inversão"""
        try:
            rsi = self.calcular_rsi(df, self.rsi_periodo)
            preco_atual = df['close'].iloc[-1]
            
            # Sinal de COMPRA (acumula)
            if rsi < self.rsi_sobrevenda:
                logger.info(f"🟢 Sinal COMPRA - RSI {rsi:.2f}")
                self.abrir_posicao_compra(preco_atual)
            
            # Sinal de VENDA (fecha todas e inverte)
            elif rsi > self.rsi_sobrecompra:
                if len(self.posicoes_abertas) > 0:
                    logger.info(f"🔴 Fechando todas as posições - RSI {rsi:.2f}")
                    self.fechar_todas_posicoes(preco_atual)
                    
        except Exception as e:
            logger.error(f"Erro na Estratégia 2: {e}")
    
    def executar_estrategia_3(self, df: pd.DataFrame):
        """Estratégia 3: RSI Acumulação com Saída RSI 50"""
        try:
            rsi = self.calcular_rsi(df, self.rsi_periodo)
            preco_atual = df['close'].iloc[-1]
            
            # Mostra informações da análise
            logger.info(f"📊 Análise: RSI={rsi:.2f} | Sobrevenda<{self.rsi_sobrevenda} | Posições abertas: {len(self.posicoes_abertas)}")
            
            # Sinal de COMPRA
            if rsi < self.rsi_sobrevenda:
                logger.info(f"🟢 Sinal COMPRA - RSI {rsi:.2f}")
                self.abrir_posicao_compra(preco_atual)
            
            # Saída quando RSI volta a 50
            elif len(self.posicoes_abertas) > 0 and abs(rsi - self.rsi_saida_meio) < 5:
                logger.info(f"🔄 RSI próximo de 50 ({rsi:.2f}) - Fechando posições")
                self.fechar_todas_posicoes(preco_atual)
                
        except Exception as e:
            logger.error(f"Erro na Estratégia 3: {e}")
    
    def executar_estrategia_4(self, df: pd.DataFrame):
        """Estratégia 4: Candle + MA21 + RSI Pullback"""
        try:
            rsi = self.calcular_rsi(df, self.rsi_periodo_est4)
            ma21 = self.calcular_ma(df, self.ma21_periodo_est4)
            preco_atual = df['close'].iloc[-1]
            candle_atual = df.iloc[-1]
            
            # Mostra análise detalhada
            logger.info(f"📊 Análise Est.4:")
            logger.info(f"   Preço: {preco_atual:.2f} | MA21: {ma21:.2f} | RSI: {rsi:.2f}")
            logger.info(f"   Preço > MA21? {'✅ SIM' if preco_atual > ma21 else '❌ NÃO'}")
            logger.info(f"   RSI < {self.rsi_sobrecompra}? {'✅ SIM' if rsi < self.rsi_sobrecompra else '❌ NÃO'}")
            logger.info(f"   Sem posições? {'✅ SIM' if len(self.posicoes_abertas) == 0 else '❌ NÃO'}")
            
            # Sinal de COMPRA
            if (preco_atual > ma21 and 
                rsi < self.rsi_sobrecompra and 
                len(self.posicoes_abertas) == 0):
                
                logger.info(f"🟢 TODAS AS CONDIÇÕES ATENDIDAS - ABRINDO COMPRA!")
                self.abrir_posicao_compra(
                    preco_atual,
                    self.stop_loss_percent_est4,
                    self.take_profit_percent_est4
                )
            
            # Verifica SL/TP
            self.verificar_stop_loss_take_profit(preco_atual)
                
        except Exception as e:
            logger.error(f"Erro na Estratégia 4: {e}")
    
    def executar_estrategia_5(self, df: pd.DataFrame):
        """Estratégia 5: MA21 + MA5 + RSI"""
        try:
            ma21 = self.calcular_ma(df, self.ma21_periodo)
            ma5 = self.calcular_ma(df, self.ma5_periodo)
            rsi = self.calcular_rsi(df, self.rsi_periodo_est5)
            preco_atual = df['close'].iloc[-1]
            
            # Mostra análise detalhada
            logger.info(f"📊 Análise Est.5:")
            logger.info(f"   Preço: {preco_atual:.2f} | MA5: {ma5:.2f} | MA21: {ma21:.2f} | RSI: {rsi:.2f}")
            logger.info(f"   MA5 > MA21? {'✅ SIM' if ma5 > ma21 else '❌ NÃO'}")
            logger.info(f"   RSI < {self.rsi_sobrecompra}? {'✅ SIM' if rsi < self.rsi_sobrecompra else '❌ NÃO'}")
            logger.info(f"   Sem posições? {'✅ SIM' if len(self.posicoes_abertas) == 0 else '❌ NÃO'}")
            
            # Sinal de COMPRA
            if (ma5 > ma21 and 
                rsi < self.rsi_sobrecompra and 
                len(self.posicoes_abertas) == 0):
                
                logger.info(f"🟢 TODAS AS CONDIÇÕES ATENDIDAS - ABRINDO COMPRA!")
                self.abrir_posicao_compra(
                    preco_atual,
                    self.stop_loss_percent_est5,
                    self.take_profit_percent_est5
                )
            
            # Verifica SL/TP
            self.verificar_stop_loss_take_profit(preco_atual)
                
        except Exception as e:
            logger.error(f"Erro na Estratégia 5: {e}")
    
    def executar_estrategia_11(self, df: pd.DataFrame):
        """Estratégia 11: Bollinger Bands - Múltiplas Posições"""
        try:
            upper_band, middle_band, lower_band = self.calcular_bollinger_bands(
                df, self.bb_periodo, self.bb_desvio
            )
            preco_atual = df['close'].iloc[-1]
            
            logger.info(f"📊 BB: Superior={upper_band:.2f} | Meio={middle_band:.2f} | Inferior={lower_band:.2f} | Preço={preco_atual:.2f}")
            
            # Sinal de COMPRA (preço toca banda inferior)
            if preco_atual <= lower_band:
                logger.info(f"🟢 Sinal COMPRA - Preço na banda inferior")
                logger.info(f"   Preço: {preco_atual:.2f} | Banda Inferior: {lower_band:.2f}")
                self.abrir_posicao_compra(
                    preco_atual,
                    self.stop_loss_percent_est11,
                    self.take_profit_percent_est11
                )
            
            # Sinal de VENDA (preço toca banda superior)
            elif preco_atual >= upper_band and len(self.posicoes_abertas) > 0:
                logger.info(f"🔴 Sinal VENDA - Preço na banda superior")
                logger.info(f"   Preço: {preco_atual:.2f} | Banda Superior: {upper_band:.2f}")
                self.fechar_todas_posicoes(preco_atual)
            
            # Verifica SL/TP
            self.verificar_stop_loss_take_profit(preco_atual)
                
        except Exception as e:
            logger.error(f"Erro na Estratégia 11: {e}")
    
    # =========================================================================
    # CONTROLE E ESTATÍSTICAS
    # =========================================================================
    
    def verificar_horario_negociacao(self) -> bool:
        """Verifica se está dentro do horário de negociação"""
        if not self.usar_horario:
            return True
        
        agora = datetime.now().time()
        inicio = datetime.strptime(self.hora_inicio, "%H:%M").time()
        fim = datetime.strptime(self.hora_fim, "%H:%M").time()
        
        return inicio <= agora <= fim
    
    def verificar_metas(self) -> bool:
        """Verifica se as metas foram atingidas"""
        if self.lucro_diario >= self.meta_diaria:
            logger.info(f"🎯 Meta diária atingida! Lucro: {self.lucro_diario:.2f} USDT")
            return True
        
        if self.lucro_total >= self.meta_total:
            logger.info(f"🎯 Meta total atingida! Lucro: {self.lucro_total:.2f} USDT")
            return True
        
        return False
    
    def _mostrar_estatisticas(self):
        """Mostra estatísticas atualizadas"""
        win_rate = (self.trades_vencedores / self.total_trades * 100) if self.total_trades > 0 else 0
        
        logger.info("-" * 60)
        logger.info("📊 ESTATÍSTICAS")
        logger.info(f"   Total de trades: {self.total_trades}")
        logger.info(f"   Trades vencedores: {self.trades_vencedores}")
        logger.info(f"   Win Rate: {win_rate:.1f}%")
        logger.info(f"   Lucro diário: {self.lucro_diario:.2f} USDT")
        logger.info(f"   Lucro total: {self.lucro_total:.2f} USDT")
        logger.info(f"   Posições abertas: {len(self.posicoes_abertas)}")
        logger.info("-" * 60)
    
    # =========================================================================
    # LOOP PRINCIPAL
    # =========================================================================
    
    def executar(self):
        """Loop principal do bot"""
        logger.info("🚀 Bot iniciado!")
        
        try:
            while self.ea_ativo:
                # Verifica horário
                if not self.verificar_horario_negociacao():
                    logger.debug("Fora do horário de negociação")
                    time.sleep(60)
                    continue
                
                # Verifica metas
                if self.verificar_metas():
                    logger.info("✅ Metas atingidas! Encerrando...")
                    break
                
                # Obtém candles
                df = self.obter_candles(100)
                if df is None or len(df) < 50:
                    logger.warning("Dados insuficientes, aguardando...")
                    time.sleep(30)
                    continue
                
                preco_atual = df['close'].iloc[-1]
                logger.info(f"💹 {self.par_negociacao}: {preco_atual:.8f} USDT")
                
                # Executa estratégia escolhida
                if self.estrategia_escolhida == 1:
                    self.executar_estrategia_1(df)
                elif self.estrategia_escolhida == 2:
                    self.executar_estrategia_2(df)
                elif self.estrategia_escolhida == 3:
                    self.executar_estrategia_3(df)
                elif self.estrategia_escolhida == 4:
                    self.executar_estrategia_4(df)
                elif self.estrategia_escolhida == 5:
                    self.executar_estrategia_5(df)
                elif self.estrategia_escolhida == 11:
                    self.executar_estrategia_11(df)
                else:
                    logger.warning(f"Estratégia {self.estrategia_escolhida} não implementada")
                
                # Aguarda próxima iteração
                time.sleep(30)  # Verifica a cada 30 segundos
                
        except KeyboardInterrupt:
            logger.info("⚠️ Bot interrompido pelo usuário")
        except Exception as e:
            logger.error(f"❌ Erro no loop principal: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            # Fecha todas as posições ao encerrar
            if len(self.posicoes_abertas) > 0:
                logger.info("🔄 Fechando todas as posições abertas...")
                df = self.obter_candles(10)
                if df is not None:
                    preco_atual = df['close'].iloc[-1]
                    self.fechar_todas_posicoes(preco_atual)
            
            self._mostrar_estatisticas()
            self.desconectar()

# =============================================================================
# MAIN
# =============================================================================
def main():
    """Função principal"""
    bot = BinancePriceActionBot()
    
    if bot.conectar():
        bot.executar()
    else:
        logger.error("Falha na conexão. Verifique suas credenciais.")

if __name__ == "__main__":
    main()
