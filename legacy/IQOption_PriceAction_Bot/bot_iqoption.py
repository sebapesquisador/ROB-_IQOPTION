# -*- coding: utf-8 -*-
"""
EA PRICE ACTION v2.0 - Adaptado para IQ Option
Bot de Trading Automático com 11 Estratégias
"""

import time
import json
import logging
from datetime import datetime, timedelta
from iqoptionapi.stable_api import IQ_Option
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import requests
from threading import Thread

# =============================================================================
# CONFIGURAÇÕES DE LOG
# =============================================================================
logging.basicConfig(
    level=logging.INFO,  # Modo INFO - apenas informações importantes
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_iqoption.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# =============================================================================
# CLASSE PRINCIPAL DO BOT
# =============================================================================
class IQOptionPriceActionBot:
    """Bot de trading para IQ Option com 10 estratégias de Price Action"""
    
    def __init__(self):
        """Inicializa o bot"""
        # ===== CREDENCIAIS IQ OPTION =====
        self.email = ""  # REMOVIDO - use .env  # ← COLOQUE SEU EMAIL AQUI
        self.senha = ""  # REMOVIDO - use .env  # ← COLOQUE SUA SENHA AQUI
        
        # ===== CONFIGURAÇÕES GERAIS =====
        self.estrategia_escolhida = 3  # 1 a 11
        self.ativo_base = "EURUSD"  # Par de moedas BASE (sem -OTC)
        self.timeframe = 5  # Tempo do candle em MINUTOS (1, 5, 15, etc)
        self.valor_operacao = 5.0  # Valor em $ por operação
        self.modo_pratica = True  # True = Conta DEMO | False = Conta REAL
        self.usar_otc_automatico = True  # True = Usa OTC fora do horário normal
        self.tempo_expiracao = 1  # Tempo de expiração em minutos
        
        # ===== PARÂMETROS RSI (Estratégias 1, 2, 3) =====
        self.rsi_periodo = 10
        self.rsi_sobrevenda = 25.0
        self.rsi_sobrecompra = 75.0
        self.rsi_saida_meio = 50.0
        
        # ===== PARÂMETROS ESTRATÉGIA 4 =====
        self.ma21_periodo_est4 = 21
        self.rsi_periodo_est4 = 14
        self.stop_loss_est4 = 200.0
        self.take_profit_est4 = 100.0
        
        # ===== PARÂMETROS ESTRATÉGIAS 5 e 6 =====
        self.ma21_periodo = 21
        self.ma5_periodo = 5
        self.rsi_periodo_est5 = 14
        self.stop_loss_est5 = 200.0
        self.take_profit_est5 = 100.0
        
        # ===== PARÂMETROS ESTRATÉGIAS 7 e 8 =====
        self.ma21_periodo_est7 = 21
        self.stop_loss_est7 = 200.0
        self.take_profit_est7 = 100.0
        
        self.ma21_periodo_est8 = 21
        self.stop_loss_est8 = 500.0
        self.take_profit_est8 = 1000.0
        
        # ===== PARÂMETROS ESTRATÉGIAS 9 e 10 =====
        self.ma21_periodo_est9 = 21
        self.stop_loss_est9 = 200.0
        self.take_profit_est9 = 100.0
        
        self.ma21_periodo_est10 = 21
        self.stop_loss_est10 = 200.0
        self.take_profit_est10 = 100.0
        
        # ===== PARÂMETROS ESTRATÉGIA 11 - BANDAS DE BOLLINGER =====
        self.bb_periodo = 20  # Período para cálculo das Bandas de Bollinger
        self.bb_desvio = 2.8  # Número de desvios padrão
        self.stop_loss_est11 = 200.0  # Stop Loss em pips
        self.take_profit_est11 = 100.0  # Take Profit em pips
        
        # ===== METAS =====
        self.meta_diaria = 5000.0
        self.meta_total = 5000.0
        
        # ===== HORÁRIO DE NEGOCIAÇÃO =====
        self.usar_horario = True
        self.hora_inicio = "00:00"
        self.hora_fim = "23:59"
        
        # ===== TRAILING STOP =====
        self.usar_trailing_stop = False
        self.trailing_distance = 100.0
        self.trailing_step = 50.0
        
        # ===== VARIÁVEIS DE CONTROLE =====
        self.api = None
        self.conectado = False
        self.ea_ativo = True
        self.lucro_total = 0.0
        self.lucro_diario = 0.0
        self.total_trades = 0
        self.trades_vencedores = 0
        self.posicao_aberta = None
        self.ultimo_candle_entrada = None
        self.ultimo_candle_compra = None
        self.ultimo_candle_venda = None
        self.rsi_anterior = 50.0
        self.aguardando_pullback_compra = False
        self.aguardando_pullback_venda = False
        self.ativo = self.ativo_base  # Será ajustado para OTC se necessário
        self.usando_otc = False
        
        # ===== DASHBOARD CONFIG =====
        self.dashboard_url = "http://127.0.0.1:5001"
        self.dashboard_enabled = True
        self.trade_history = []  # Histórico de trades
        
    # =========================================================================
    # DETECÇÃO AUTOMÁTICA DE OTC
    # =========================================================================
    
    def obter_ativo_correto(self) -> str:
        """
        Retorna o ativo correto (com ou sem OTC) baseado no horário
        Mercado FOREX: Segunda 00:00 GMT até Sexta 21:00 GMT
        Fora desse horário ou fim de semana: usa OTC
        """
        if not self.usar_otc_automatico:
            return self.ativo_base
        
        agora = datetime.utcnow()
        dia_semana = agora.weekday()  # 0=Segunda, 6=Domingo
        hora = agora.hour
        
        # Debug: mostra horário atual
        logger.debug(f"UTC: {agora} | Dia: {dia_semana} | Hora: {hora}")
        
        # Fim de semana (Sábado ou Domingo)
        if dia_semana >= 5:
            if not self.usando_otc:
                logger.info(f"🔄 Fim de semana detectado - Usando {self.ativo_base}-OTC")
                self.usando_otc = True
            return f"{self.ativo_base}-OTC"
        
        # Sexta após 21:00 GMT
        if dia_semana == 4 and hora >= 21:
            if not self.usando_otc:
                logger.info(f"🔄 Mercado fechando - Usando {self.ativo_base}-OTC")
                self.usando_otc = True
            return f"{self.ativo_base}-OTC"
        
        # Segunda antes das 00:00 GMT (tecnicamente impossível, mas por segurança)
        if dia_semana == 0 and hora < 1:
            if not self.usando_otc:
                logger.info(f"🔄 Mercado ainda fechado - Usando {self.ativo_base}-OTC")
                self.usando_otc = True
            return f"{self.ativo_base}-OTC"
        
        # FORÇAR OTC se estiver fora do horário comercial (horário brasileiro noturno)
        # Horário de Brasília = UTC-3, então 20:28 BRT = 23:28 UTC
        # Mercado FOREX fecha sexta 18:00 EST e abre domingo 17:00 EST
        # Vamos usar OTC sempre que não for horário comercial de NY (13:30-20:00 UTC)
        if hora < 13 or hora >= 20:
            if not self.usando_otc:
                logger.info(f"🔄 Fora do horário comercial - Usando {self.ativo_base}-OTC")
                self.usando_otc = True
            return f"{self.ativo_base}-OTC"
        
        # Horário normal do mercado
        if self.usando_otc:
            logger.info(f"🔄 Mercado aberto - Usando {self.ativo_base}")
            self.usando_otc = False
        return self.ativo_base
    
    # =========================================================================
    # DASHBOARD / PAINEL WEB
    # =========================================================================
    
    def atualizar_painel(self):
        """Atualiza o painel web com dados do bot"""
        if not self.dashboard_enabled:
            return
        
        try:
            payload = {
                "ativo": self.ativo,
                "timeframe": f"{self.timeframe}m",
                "estrategia": str(self.estrategia_escolhida),
                "lucro_diario": round(self.lucro_diario, 2),
                "lucro_total": round(self.lucro_total, 2),
                "total_trades": self.total_trades,
                "wins": self.trades_vencedores
            }
            
            requests.post(
                f"{self.dashboard_url}/update",
                json=payload,
                timeout=2
            )
        except Exception as e:
            # Não para o bot se o painel falhar
            logger.debug(f"Falha ao atualizar painel: {e}")
    
    def enviar_trade_ao_painel(self, direcao: str, resultado: str, lucro: float, preco: float):
        """Envia trade individual ao histórico do painel"""
        if not self.dashboard_enabled:
            return
        
        try:
            trade = {
                "timestamp": datetime.now().isoformat(),
                "ativo": self.ativo,
                "direcao": direcao,
                "resultado": resultado,  # "WIN" ou "LOSS"
                "lucro": round(lucro, 2),
                "preco": round(preco, 5)
            }
            
            requests.post(
                f"{self.dashboard_url}/add_trade",
                json=trade,
                timeout=2
            )
        except Exception as e:
            logger.debug(f"Falha ao enviar trade ao painel: {e}")
    
    # =========================================================================
    # CONEXÃO COM IQ OPTION
    # =========================================================================
    
    def conectar(self) -> bool:
        """Conecta à API da IQ Option"""
        try:
            logger.info("=" * 60)
            logger.info("INICIANDO CONEXÃO COM IQ OPTION")
            logger.info("=" * 60)
            
            self.api = IQ_Option(self.email, self.senha)
            check, reason = self.api.connect()
            
            if check:
                self.conectado = True
                
                # Define modo de operação (DEMO ou REAL)
                if self.modo_pratica:
                    self.api.change_balance("PRACTICE")
                    logger.info("✅ Modo: CONTA DEMO")
                else:
                    self.api.change_balance("REAL")
                    logger.warning("⚠️ Modo: CONTA REAL")
                
                # Mostra saldo
                saldo = self.api.get_balance()
                logger.info(f"💰 Saldo disponível: ${saldo:.2f}")
                
                # Define ativo correto (OTC se necessário)
                self.ativo = self.obter_ativo_correto()
                
                # Mostra configurações
                logger.info("-" * 60)
                logger.info(f"📊 Ativo: {self.ativo}")
                if self.usando_otc:
                    logger.info(f"   🌐 Modo OTC ativado (mercado 24/7)")
                logger.info(f"⏱️ Timeframe: {self.timeframe} minuto(s)")
                logger.info(f"⏳ Expiração: {self.tempo_expiracao} minuto(s)")
                logger.info(f"💵 Valor por operação: ${self.valor_operacao}")
                logger.info(f"🎯 Estratégia: {self.estrategia_escolhida}")
                logger.info(f"🕒 Horário: {self.hora_inicio} - {self.hora_fim}")
                
                # Verifica se ativo está disponível
                logger.info("-" * 60)
                logger.info("🔍 Verificando disponibilidade do ativo...")
                try:
                    # Tenta obter informações do ativo
                    all_assets = self.api.get_all_open_time()
                    
                    # Lista ativos OTC disponíveis
                    ativos_otc = []
                    if 'digital' in all_assets and isinstance(all_assets['digital'], dict):
                        for ativo_nome in all_assets['digital'].keys():
                            if '-OTC' in ativo_nome or 'OTC' in ativo_nome:
                                ativos_otc.append(ativo_nome)
                    
                    if 'binary' in all_assets and isinstance(all_assets['binary'], dict):
                        for ativo_nome in all_assets['binary'].keys():
                            if '-OTC' in ativo_nome or 'OTC' in ativo_nome:
                                if ativo_nome not in ativos_otc:
                                    ativos_otc.append(ativo_nome)
                    
                    if ativos_otc:
                        logger.info(f"💡 Ativos OTC disponíveis: {', '.join(ativos_otc[:10])}")
                    
                    # Verifica o ativo escolhido
                    if 'binary' in all_assets and self.ativo in all_assets.get('binary', {}):
                        logger.info(f"✅ {self.ativo} disponível em Binary Options")
                    else:
                        logger.warning(f"⚠️ {self.ativo} NÃO encontrado em Binary Options")
                    
                    if 'digital' in all_assets and self.ativo in all_assets.get('digital', {}):
                        logger.info(f"✅ {self.ativo} disponível em Digital Options")
                    else:
                        logger.warning(f"⚠️ {self.ativo} NÃO encontrado em Digital Options")
                        
                except Exception as e:
                    logger.warning(f"⚠️ Erro ao verificar disponibilidade: {e}")
                    import traceback
                    logger.debug(traceback.format_exc())
                
                logger.info("=" * 60)
                
                return True
            else:
                logger.error(f"❌ Falha na conexão: {reason}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Erro ao conectar: {e}")
            return False
    
    def desconectar(self):
        """Desconecta da API"""
        try:
            if self.api:
                # Tenta fechar a conexão websocket
                if hasattr(self.api, 'close'):
                    self.api.close()
                elif hasattr(self.api, 'websocket') and self.api.websocket:
                    self.api.websocket.close()
                logger.info("🔌 Desconectado da IQ Option")
        except Exception as e:
            logger.warning(f"⚠️ Erro ao desconectar: {e}")
    
    # =========================================================================
    # OBTENÇÃO DE DADOS
    # =========================================================================
    
    def obter_candles(self, quantidade: int = 100) -> Optional[pd.DataFrame]:
        """Obtém histórico de candles"""
        try:
            # Timeframe em segundos
            timeframe_segundos = self.timeframe * 60
            
            # Busca candles
            candles = self.api.get_candles(
                self.ativo,
                timeframe_segundos,
                quantidade,
                time.time()
            )
            
            if not candles:
                logger.error("❌ Nenhum candle retornado")
                return None
            
            # Converte para DataFrame
            df = pd.DataFrame(candles)
            
            # Verifica quais colunas existem
            if 'from' in df.columns:
                df['time'] = pd.to_datetime(df['from'], unit='s')
            elif 'at' in df.columns:
                df['time'] = pd.to_datetime(df['at'], unit='s')
            else:
                df['time'] = pd.to_datetime(df.index, unit='s')
            
            # Cria colunas high e low se não existirem
            if 'high' not in df.columns:
                df['high'] = df['close']
            if 'low' not in df.columns:
                df['low'] = df['close']
            if 'volume' not in df.columns:
                df['volume'] = 0
            
            # Seleciona apenas as colunas necessárias
            df = df[['time', 'open', 'close', 'high', 'low', 'volume']]
            df = df.sort_values('time').reset_index(drop=True)
            
            return df
            
        except Exception as e:
            logger.error(f"❌ Erro ao obter candles: {e}")
            return None
    
    # =========================================================================
    # INDICADORES TÉCNICOS
    # =========================================================================
    
    def calcular_rsi(self, df: pd.DataFrame, periodo: int) -> pd.Series:
        """Calcula o RSI"""
        delta = df['close'].diff()
        ganho = (delta.where(delta > 0, 0)).rolling(window=periodo).mean()
        perda = (-delta.where(delta < 0, 0)).rolling(window=periodo).mean()
        
        rs = ganho / perda
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def calcular_ma(self, df: pd.DataFrame, periodo: int, tipo: str = 'EMA') -> pd.Series:
        """Calcula Média Móvel"""
        if tipo == 'EMA':
            return df['close'].ewm(span=periodo, adjust=False).mean()
        else:  # SMA
            return df['close'].rolling(window=periodo).mean()
    
    def calcular_bollinger_bands(self, df: pd.DataFrame, periodo: int, desvio: float) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Calcula as Bandas de Bollinger
        
        Args:
            df: DataFrame com dados de preço
            periodo: Período para média móvel
            desvio: Número de desvios padrão
            
        Returns:
            Tupla com (banda_superior, banda_media, banda_inferior)
        """
        # Calcula a média móvel simples
        banda_media = df['close'].rolling(window=periodo).mean()
        
        # Calcula o desvio padrão
        std = df['close'].rolling(window=periodo).std()
        
        # Calcula as bandas superior e inferior
        banda_superior = banda_media + (std * desvio)
        banda_inferior = banda_media - (std * desvio)
        
        return banda_superior, banda_media, banda_inferior
    
    # =========================================================================
    # EXECUÇÃO DE ORDENS
    # =========================================================================
    
    def abrir_posicao(self, direcao: str, tempo_expiracao: int = None) -> bool:
        """
        Abre uma posição na IQ Option
        
        Args:
            direcao: "CALL" (compra) ou "PUT" (venda)
            tempo_expiracao: Tempo de expiração em minutos (usa self.tempo_expiracao se None)
        """
        try:
            if tempo_expiracao is None:
                tempo_expiracao = self.tempo_expiracao
            
            # Atualiza ativo (pode mudar para OTC)
            self.ativo = self.obter_ativo_correto()
            
            logger.info(f"📈 Abrindo posição {direcao}")
            logger.info(f"   Ativo: {self.ativo} | Valor: ${self.valor_operacao} | Exp: {tempo_expiracao}min")
            
            # Verifica disponibilidade do ativo
            try:
                all_assets = self.api.get_all_open_time()
                if all_assets:
                    # Debug: mostra estrutura dos ativos
                    logger.debug(f"   🔍 Tipos de mercado disponíveis: {list(all_assets.keys())}")
                    
                    # Tenta verificar em digital
                    if 'digital' in all_assets and isinstance(all_assets['digital'], dict):
                        if self.ativo in all_assets['digital']:
                            logger.info(f"   ✅ {self.ativo} encontrado em Digital Options")
                        else:
                            logger.warning(f"   ⚠️ {self.ativo} NÃO encontrado em Digital Options")
                            # Mostra alguns ativos disponíveis
                            ativos_disponiveis = list(all_assets['digital'].keys())[:5]
                            logger.info(f"   � Exemplos de ativos Digital: {ativos_disponiveis}")
                    
                    # Tenta verificar em binary
                    if 'binary' in all_assets and isinstance(all_assets['binary'], dict):
                        if self.ativo in all_assets['binary']:
                            logger.info(f"   ✅ {self.ativo} encontrado em Binary Options")
                        else:
                            logger.warning(f"   ⚠️ {self.ativo} NÃO encontrado em Binary Options")
                            # Mostra alguns ativos disponíveis
                            ativos_disponiveis = list(all_assets['binary'].keys())[:5]
                            logger.info(f"   � Exemplos de ativos Binary: {ativos_disponiveis}")
            except Exception as e:
                logger.warning(f"   ⚠️ Erro ao verificar disponibilidade: {e}")
                import traceback
                logger.debug(traceback.format_exc())
            
            # Converte direção
            if direcao.upper() == "CALL":
                action = "call"
            elif direcao.upper() == "PUT":
                action = "put"
            else:
                logger.error(f"❌ Direção inválida: {direcao}")
                return False
            
            check = False
            order_id = None
            
            # TENTA BINARY OPTIONS PRIMEIRO (mais compatível com OTC)
            try:
                # Binary Options usa tempo de expiração em MINUTOS
                resultado = self.api.buy(
                    self.valor_operacao,
                    self.ativo,
                    action,
                    tempo_expiracao
                )
                
                if isinstance(resultado, tuple) and len(resultado) >= 2:
                    check, order_id = resultado[0], resultado[1]
                else:
                    check, order_id = resultado, None
                
                if check and order_id and order_id > 0:
                    logger.info(f"   ✅ Binary Option executada | ID: {order_id}")
                else:
                    # Captura mensagem de erro
                    msg_erro = str(order_id) if order_id else "desconhecido"
                    logger.warning(f"   ⚠️ Binary Option retornou | Check: {check} | ID: {msg_erro}")
                    
                    # Detecta ativo suspenso e tenta com OTC
                    if "suspended" in msg_erro.lower() or "cannot" in msg_erro.lower():
                        if not self.ativo.endswith("-OTC"):
                            logger.warning(f"   🔄 Ativo suspenso! Tentando com {self.ativo}-OTC...")
                            self.ativo = f"{self.ativo_base}-OTC"
                            self.usando_otc = True
                            
                            # Tenta novamente com OTC
                            resultado_otc = self.api.buy(
                                self.valor_operacao,
                                self.ativo,
                                action,
                                tempo_expiracao
                            )
                            
                            if isinstance(resultado_otc, tuple) and len(resultado_otc) >= 2:
                                check, order_id = resultado_otc[0], resultado_otc[1]
                            else:
                                check, order_id = resultado_otc, None
                            
                            if check and order_id and order_id > 0:
                                logger.info(f"   ✅ Binary Option OTC executada | ID: {order_id}")
                            else:
                                logger.warning(f"   ⚠️ OTC também falhou | Check: {check} | ID: {order_id}")
            except Exception as e:
                logger.warning(f"   ⚠️ Binary Option falhou: {e}")
                import traceback
                logger.debug(traceback.format_exc())
            
            # Se Binary falhar, tenta Digital Options
            if not check or not order_id or order_id <= 0:
                logger.info(f"   📡 Tentando Digital Option...")
                
                # Se não estiver usando OTC ainda e teve erro de suspensão, força OTC
                if not self.ativo.endswith("-OTC") and self.usar_otc_automatico:
                    logger.info(f"   🔄 Forçando OTC devido falha anterior...")
                    self.ativo = f"{self.ativo_base}-OTC"
                    self.usando_otc = True
                
                try:
                    # Digital Options - tenta diferentes tempos
                    for exp_time in [1, 2, 5]:
                        logger.info(f"      � Tentando expiração: {exp_time} minuto(s)...")
                        resultado = self.api.buy_digital_spot(
                            self.ativo,
                            self.valor_operacao,
                            action,
                            exp_time
                        )
                        logger.debug(f"      🔍 Resultado Digital ({exp_time}min): {resultado}")
                        
                        if isinstance(resultado, tuple) and len(resultado) >= 2:
                            check, order_id = resultado[0], resultado[1]
                        else:
                            check, order_id = resultado, None
                        
                        if check and order_id and order_id > 0:
                            logger.info(f"   ✅ Digital Option executada | ID: {order_id} | Exp: {exp_time}min")
                            break
                        else:
                            logger.debug(f"      ⚠️ Falhou com {exp_time}min | Check: {check} | ID: {order_id}")
                
                except Exception as e:
                    logger.warning(f"   ⚠️ Digital Option falhou: {e}")
                    import traceback
                    logger.debug(traceback.format_exc())
            
            # Verifica se teve sucesso
            if check and order_id and order_id > 0:
                self.posicao_aberta = {
                    'id': order_id,
                    'direcao': direcao,
                    'valor': self.valor_operacao,
                    'hora': datetime.now(),
                    'ativo': self.ativo
                }
                logger.info(f"✅ Posição {direcao} aberta | ID: {order_id}")
                return True
            else:
                logger.error(f"❌ Falha ao abrir posição {direcao}")
                logger.error(f"   Ativo: {self.ativo} | Valor: ${self.valor_operacao} | Expiração: {tempo_expiracao}min")
                logger.error(f"   Check: {check} | Order ID: {order_id}")
                
                # Sugestões de solução
                logger.warning("💡 Possíveis soluções:")
                logger.warning("   1. Verifique se o ativo está disponível (EURUSD-OTC pode funcionar)")
                logger.warning("   2. Tente aumentar o valor da operação (mínimo pode ser $1)")
                logger.warning("   3. Mercado pode estar fechado para este ativo")
                return False
                
        except Exception as e:
            logger.error(f"❌ Erro ao abrir posição: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def verificar_resultado_operacao(self, order_id: int):
        """Verifica o resultado de uma operação"""
        try:
            # Aguarda a operação finalizar (máximo 5 minutos)
            tempo_espera = 0
            while tempo_espera < 300:  # 5 minutos
                resultado = self.api.check_win_v3(order_id)
                
                if resultado:
                    lucro = resultado
                    
                    # Atualiza estatísticas
                    self.total_trades += 1
                    self.lucro_total += lucro
                    self.lucro_diario += lucro
                    
                    if lucro > 0:
                        self.trades_vencedores += 1
                        logger.info(f"✅ TRADE VENCEDOR | Lucro: ${lucro:.2f}")
                        resultado_str = "WIN"
                    else:
                        logger.info(f"❌ TRADE PERDEDOR | Prejuízo: ${lucro:.2f}")
                        resultado_str = "LOSS"
                    
                    # Mostra estatísticas
                    win_rate = (self.trades_vencedores / self.total_trades * 100) if self.total_trades > 0 else 0
                    logger.info(f"📊 Win Rate: {win_rate:.1f}% ({self.trades_vencedores}/{self.total_trades})")
                    logger.info(f"💰 Lucro Total: ${self.lucro_total:.2f}")
                    logger.info(f"💰 Lucro Diário: ${self.lucro_diario:.2f}")
                    
                    # Atualiza painel
                    self.atualizar_painel()
                    
                    # Envia trade ao histórico
                    preco_atual = self.api.get_digital_current_profit(self.ativo, 1) if hasattr(self.api, 'get_digital_current_profit') else 0
                    self.enviar_trade_ao_painel(
                        direcao=self.posicao_aberta.get('direcao', 'CALL'),
                        resultado=resultado_str,
                        lucro=lucro,
                        preco=preco_atual
                    )
                    
                    self.posicao_aberta = None
                    return lucro
                
                time.sleep(1)
                tempo_espera += 1
            
            logger.warning("⚠️ Timeout ao verificar resultado")
            self.posicao_aberta = None
            return 0
            
        except Exception as e:
            logger.error(f"❌ Erro ao verificar resultado: {e}")
            self.posicao_aberta = None
            return 0
    
    # =========================================================================
    # VERIFICAÇÕES
    # =========================================================================
    
    def verificar_horario(self) -> bool:
        """Verifica se está dentro do horário de negociação"""
        if not self.usar_horario:
            return True
        
        agora = datetime.now()
        hora_atual = agora.strftime("%H:%M")
        
        if self.hora_inicio <= hora_atual <= self.hora_fim:
            return True
        else:
            return False
    
    def verificar_metas(self) -> bool:
        """Verifica se as metas foram atingidas"""
        if self.meta_diaria > 0 and self.lucro_diario >= self.meta_diaria:
            logger.info(f"🎯 META DIÁRIA ATINGIDA! Lucro: ${self.lucro_diario:.2f}")
            return True
        
        if self.meta_total > 0 and self.lucro_total >= self.meta_total:
            logger.info(f"🎯 META TOTAL ATINGIDA! Lucro: ${self.lucro_total:.2f}")
            return True
        
        return False
    
    # =========================================================================
    # ESTRATÉGIAS DE TRADING
    # =========================================================================
    
    def estrategia_1_reversao(self, df: pd.DataFrame):
        """
        ESTRATÉGIA 1: REVERSÃO - Uma posição por vez
        COMPRA: RSI < Sobrevenda
        VENDA: RSI > Sobrecompra
        SAÍDA: RSI retorna ao meio (50)
        """
        if len(df) < self.rsi_periodo + 2:
            return
        
        # Calcula RSI
        df['rsi'] = self.calcular_rsi(df, self.rsi_periodo)
        rsi_atual = df['rsi'].iloc[-1]
        
        # Verifica se já tem posição aberta
        if self.posicao_aberta:
            # Lógica de saída
            if self.posicao_aberta['direcao'] == "CALL" and rsi_atual > self.rsi_saida_meio:
                logger.info(f"📊 EST 1: Saída COMPRA | RSI: {rsi_atual:.2f} > {self.rsi_saida_meio}")
                # Na IQ Option, aguarda expiração automática
            elif self.posicao_aberta['direcao'] == "PUT" and rsi_atual < self.rsi_saida_meio:
                logger.info(f"📊 EST 1: Saída VENDA | RSI: {rsi_atual:.2f} < {self.rsi_saida_meio}")
                # Na IQ Option, aguarda expiração automática
        else:
            # Verifica novo candle
            candle_atual = df['time'].iloc[-1]
            if candle_atual == self.ultimo_candle_entrada:
                return
            
            # Sinais de entrada
            if rsi_atual < self.rsi_sobrevenda:
                logger.info(f"📊 EST 1: Sinal COMPRA | RSI: {rsi_atual:.2f}")
                if self.abrir_posicao("CALL"):
                    self.ultimo_candle_entrada = candle_atual
            
            elif rsi_atual > self.rsi_sobrecompra:
                logger.info(f"📊 EST 1: Sinal VENDA | RSI: {rsi_atual:.2f}")
                if self.abrir_posicao("PUT"):
                    self.ultimo_candle_entrada = candle_atual
    
    def estrategia_2_acumulacao(self, df: pd.DataFrame):
        """
        ESTRATÉGIA 2: ACUMULAÇÃO COM INVERSÃO
        Acumula posições a cada cruzamento do RSI
        Inverte quando RSI cruza para o outro lado
        """
        if len(df) < self.rsi_periodo + 2:
            return
        
        # Calcula RSI
        df['rsi'] = self.calcular_rsi(df, self.rsi_periodo)
        rsi_atual = df['rsi'].iloc[-1]
        
        # Detecta cruzamentos
        cruzou_para_baixo_30 = self.rsi_anterior >= self.rsi_sobrevenda and rsi_atual < self.rsi_sobrevenda
        cruzou_para_cima_70 = self.rsi_anterior <= self.rsi_sobrecompra and rsi_atual > self.rsi_sobrecompra
        
        candle_atual = df['time'].iloc[-1]
        
        # Lógica de inversão
        if cruzou_para_cima_70 and candle_atual != self.ultimo_candle_venda:
            logger.info(f"📊 EST 2: INVERSÃO para VENDA | RSI: {rsi_atual:.2f}")
            if self.abrir_posicao("PUT"):
                self.ultimo_candle_venda = candle_atual
        
        elif cruzou_para_baixo_30 and candle_atual != self.ultimo_candle_compra:
            logger.info(f"📊 EST 2: INVERSÃO para COMPRA | RSI: {rsi_atual:.2f}")
            if self.abrir_posicao("CALL"):
                self.ultimo_candle_compra = candle_atual
        
        # Atualiza RSI anterior
        self.rsi_anterior = rsi_atual
    
    def estrategia_3_acumulacao_rsi50(self, df: pd.DataFrame):
        """
        ESTRATÉGIA 3: ACUMULAÇÃO COM SAÍDA RSI 50
        Acumula posições e fecha todas quando RSI volta ao meio
        """
        if len(df) < self.rsi_periodo + 2:
            return
        
        # Calcula RSI
        df['rsi'] = self.calcular_rsi(df, self.rsi_periodo)
        rsi_atual = df['rsi'].iloc[-1]
        
        # Detecta cruzamentos
        cruzou_para_baixo_30 = self.rsi_anterior >= self.rsi_sobrevenda and rsi_atual < self.rsi_sobrevenda
        cruzou_para_cima_70 = self.rsi_anterior <= self.rsi_sobrecompra and rsi_atual > self.rsi_sobrecompra
        
        candle_atual = df['time'].iloc[-1]
        
        # Entrada: Compra
        if cruzou_para_baixo_30 and candle_atual != self.ultimo_candle_compra:
            logger.info(f"📊 EST 3: Abrindo COMPRA | RSI: {rsi_atual:.2f}")
            if self.abrir_posicao("CALL"):
                self.ultimo_candle_compra = candle_atual
        
        # Entrada: Venda
        if cruzou_para_cima_70 and candle_atual != self.ultimo_candle_venda:
            logger.info(f"📊 EST 3: Abrindo VENDA | RSI: {rsi_atual:.2f}")
            if self.abrir_posicao("PUT"):
                self.ultimo_candle_venda = candle_atual
        
        # Saída: RSI volta ao meio
        if self.posicao_aberta:
            if self.posicao_aberta['direcao'] == "CALL" and rsi_atual >= self.rsi_saida_meio:
                logger.info(f"📊 EST 3: Saída COMPRA | RSI: {rsi_atual:.2f} >= {self.rsi_saida_meio}")
            
            elif self.posicao_aberta['direcao'] == "PUT" and rsi_atual <= self.rsi_saida_meio:
                logger.info(f"📊 EST 3: Saída VENDA | RSI: {rsi_atual:.2f} <= {self.rsi_saida_meio}")
        
        # Atualiza RSI anterior
        self.rsi_anterior = rsi_atual
    
    def estrategia_4_pullback_ma21(self, df: pd.DataFrame):
        """
        ESTRATÉGIA 4: CANDLE + MA21 + RSI PULLBACK
        Setup: Candle a favor da tendência + RSI confirmando
        Entrada: Preço toca a MA21 (pullback)
        """
        if len(df) < max(self.ma21_periodo_est4, self.rsi_periodo_est4) + 2:
            return
        
        # Calcula indicadores
        df['ma21'] = self.calcular_ma(df, self.ma21_periodo_est4, 'EMA')
        df['rsi'] = self.calcular_rsi(df, self.rsi_periodo_est4)
        
        # Candle anterior (fechado)
        candle_fechado = df.iloc[-2]
        close_fechado = candle_fechado['close']
        open_fechado = candle_fechado['open']
        ma21_fechado = candle_fechado['ma21']
        rsi_fechado = candle_fechado['rsi']
        
        # Candle atual
        candle_atual_data = df['time'].iloc[-1]
        close_atual = df['close'].iloc[-1]
        ma21_atual = df['ma21'].iloc[-1]
        
        # SETUP DE COMPRA: Close > Open E Close > MA21 E RSI > 50
        if close_fechado > open_fechado and close_fechado > ma21_fechado and rsi_fechado > 50.0:
            if not self.aguardando_pullback_compra:
                self.aguardando_pullback_compra = True
                self.aguardando_pullback_venda = False
                logger.info(f"📊 EST 4: SETUP COMPRA detectado | Aguardando pullback à MA21")
        
        # SETUP DE VENDA: Close < Open E Close < MA21 E RSI < 50
        if close_fechado < open_fechado and close_fechado < ma21_fechado and rsi_fechado < 50.0:
            if not self.aguardando_pullback_venda:
                self.aguardando_pullback_venda = True
                self.aguardando_pullback_compra = False
                logger.info(f"📊 EST 4: SETUP VENDA detectado | Aguardando pullback à MA21")
        
        # ENTRADA: Pullback à MA21
        tolerancia = ma21_atual * 0.002  # 0.2% de tolerância
        
        if self.aguardando_pullback_compra and not self.posicao_aberta:
            if abs(close_atual - ma21_atual) <= tolerancia:
                logger.info(f"📊 EST 4: PULLBACK COMPRA! Preço: {close_atual:.5f} | MA21: {ma21_atual:.5f}")
                if self.abrir_posicao("CALL"):
                    self.aguardando_pullback_compra = False
        
        if self.aguardando_pullback_venda and not self.posicao_aberta:
            if abs(close_atual - ma21_atual) <= tolerancia:
                logger.info(f"📊 EST 4: PULLBACK VENDA! Preço: {close_atual:.5f} | MA21: {ma21_atual:.5f}")
                if self.abrir_posicao("PUT"):
                    self.aguardando_pullback_venda = False
    
    def estrategia_5_ma_rsi(self, df: pd.DataFrame):
        """
        ESTRATÉGIA 5: MA21 + MA5 + RSI
        COMPRA: Close > MA21 E Close > MA5 E RSI > 50
        VENDA: Close < MA21 E Close < MA5 E RSI < 50
        SAÍDA: Retorno à MA5 ou TP
        """
        if len(df) < max(self.ma21_periodo, self.ma5_periodo, self.rsi_periodo_est5) + 2:
            return
        
        # Calcula indicadores
        df['ma21'] = self.calcular_ma(df, self.ma21_periodo, 'EMA')
        df['ma5'] = self.calcular_ma(df, self.ma5_periodo, 'EMA')
        df['rsi'] = self.calcular_rsi(df, self.rsi_periodo_est5)
        
        # Candle fechado
        candle_fechado = df.iloc[-2]
        close_fechado = candle_fechado['close']
        ma21_fechado = candle_fechado['ma21']
        ma5_fechado = candle_fechado['ma5']
        rsi_fechado = candle_fechado['rsi']
        
        # Candle atual
        candle_atual_data = df['time'].iloc[-1]
        close_atual = df['close'].iloc[-1]
        ma5_atual = df['ma5'].iloc[-1]
        
        # Verifica saída se tem posição
        if self.posicao_aberta:
            if self.posicao_aberta['direcao'] == "CALL" and close_atual <= ma5_atual:
                logger.info(f"📊 EST 5: SAÍDA COMPRA - Retorno à MA5")
                return
            
            elif self.posicao_aberta['direcao'] == "PUT" and close_atual >= ma5_atual:
                logger.info(f"📊 EST 5: SAÍDA VENDA - Retorno à MA5")
                return
            
            return
        
        # Sinais de entrada
        sinal_compra = (close_fechado > ma21_fechado and 
                       close_fechado > ma5_fechado and 
                       rsi_fechado > 50.0)
        
        sinal_venda = (close_fechado < ma21_fechado and 
                      close_fechado < ma5_fechado and 
                      rsi_fechado < 50.0)
        
        if sinal_compra and candle_atual_data != self.ultimo_candle_compra:
            logger.info(f"📊 EST 5: COMPRA | Close > MA21 > MA5 | RSI: {rsi_fechado:.2f}")
            if self.abrir_posicao("CALL"):
                self.ultimo_candle_compra = candle_atual_data
        
        elif sinal_venda and candle_atual_data != self.ultimo_candle_venda:
            logger.info(f"📊 EST 5: VENDA | Close < MA21 < MA5 | RSI: {rsi_fechado:.2f}")
            if self.abrir_posicao("PUT"):
                self.ultimo_candle_venda = candle_atual_data
    
    def estrategia_6_ma_rsi_invertido(self, df: pd.DataFrame):
        """
        ESTRATÉGIA 6: MA21 + MA5 + RSI INVERTIDO (Contra-tendência)
        VENDA: Close > MA21 E Close > MA5 E RSI > 50 (contra a alta)
        COMPRA: Close < MA21 E Close < MA5 E RSI < 50 (contra a baixa)
        """
        if len(df) < max(self.ma21_periodo, self.ma5_periodo, self.rsi_periodo_est5) + 2:
            return
        
        # Calcula indicadores
        df['ma21'] = self.calcular_ma(df, self.ma21_periodo, 'EMA')
        df['ma5'] = self.calcular_ma(df, self.ma5_periodo, 'EMA')
        df['rsi'] = self.calcular_rsi(df, self.rsi_periodo_est5)
        
        # Candle fechado
        candle_fechado = df.iloc[-2]
        close_fechado = candle_fechado['close']
        ma21_fechado = candle_fechado['ma21']
        ma5_fechado = candle_fechado['ma5']
        rsi_fechado = candle_fechado['rsi']
        
        # Candle atual
        candle_atual_data = df['time'].iloc[-1]
        close_atual = df['close'].iloc[-1]
        ma5_atual = df['ma5'].iloc[-1]
        
        # Verifica saída se tem posição
        if self.posicao_aberta:
            if self.posicao_aberta['direcao'] == "CALL" and close_atual <= ma5_atual:
                logger.info(f"📊 EST 6: SAÍDA COMPRA - Retorno à MA5")
                return
            
            elif self.posicao_aberta['direcao'] == "PUT" and close_atual >= ma5_atual:
                logger.info(f"📊 EST 6: SAÍDA VENDA - Retorno à MA5")
                return
            
            return
        
        # Sinais INVERTIDOS
        sinal_venda = (close_fechado > ma21_fechado and 
                      close_fechado > ma5_fechado and 
                      rsi_fechado > 50.0)
        
        sinal_compra = (close_fechado < ma21_fechado and 
                       close_fechado < ma5_fechado and 
                       rsi_fechado < 50.0)
        
        if sinal_venda and candle_atual_data != self.ultimo_candle_venda:
            logger.info(f"📊 EST 6 (INVERTIDO): VENDA contra tendência de alta | RSI: {rsi_fechado:.2f}")
            if self.abrir_posicao("PUT"):
                self.ultimo_candle_venda = candle_atual_data
        
        elif sinal_compra and candle_atual_data != self.ultimo_candle_compra:
            logger.info(f"📊 EST 6 (INVERTIDO): COMPRA contra tendência de baixa | RSI: {rsi_fechado:.2f}")
            if self.abrir_posicao("CALL"):
                self.ultimo_candle_compra = candle_atual_data
    
    def estrategia_7_candle_ma21(self, df: pd.DataFrame):
        """
        ESTRATÉGIA 7: CANDLE + MA21 TENDÊNCIA
        COMPRA: Close > Open E Close > MA21
        VENDA: Close < Open E Close < MA21
        Inversão automática quando sinal muda
        """
        if len(df) < self.ma21_periodo_est7 + 2:
            return
        
        # Calcula MA21
        df['ma21'] = self.calcular_ma(df, self.ma21_periodo_est7, 'EMA')
        
        # Candle fechado
        candle_fechado = df.iloc[-2]
        close_fechado = candle_fechado['close']
        open_fechado = candle_fechado['open']
        ma21_fechado = candle_fechado['ma21']
        candle_atual_data = df['time'].iloc[-1]
        
        # Sinais
        sinal_compra = close_fechado > open_fechado and close_fechado > ma21_fechado
        sinal_venda = open_fechado > close_fechado and close_fechado < ma21_fechado
        
        if self.posicao_aberta:
            # Inversão automática
            if self.posicao_aberta['direcao'] == "CALL" and sinal_venda:
                if candle_atual_data != self.ultimo_candle_venda:
                    logger.info(f"📊 EST 7: INVERSÃO! COMPRA → VENDA")
                    if self.abrir_posicao("PUT"):
                        self.ultimo_candle_venda = candle_atual_data
            
            elif self.posicao_aberta['direcao'] == "PUT" and sinal_compra:
                if candle_atual_data != self.ultimo_candle_compra:
                    logger.info(f"📊 EST 7: INVERSÃO! VENDA → COMPRA")
                    if self.abrir_posicao("CALL"):
                        self.ultimo_candle_compra = candle_atual_data
        else:
            # Sem posição: abre conforme sinal
            if sinal_compra and candle_atual_data != self.ultimo_candle_compra:
                logger.info(f"📊 EST 7: COMPRA | Candle alta + Close > MA21")
                if self.abrir_posicao("CALL"):
                    self.ultimo_candle_compra = candle_atual_data
            
            elif sinal_venda and candle_atual_data != self.ultimo_candle_venda:
                logger.info(f"📊 EST 7: VENDA | Candle baixa + Close < MA21")
                if self.abrir_posicao("PUT"):
                    self.ultimo_candle_venda = candle_atual_data
    
    def estrategia_8_candle_ma21_invertido(self, df: pd.DataFrame):
        """
        ESTRATÉGIA 8: CANDLE + MA21 INVERTIDO (HEDGE)
        VENDA: Close > Open E Close > MA21 (contra tendência)
        COMPRA: Close < Open E Close < MA21 (contra tendência)
        """
        if len(df) < self.ma21_periodo_est8 + 2:
            return
        
        # Calcula MA21
        df['ma21'] = self.calcular_ma(df, self.ma21_periodo_est8, 'EMA')
        
        # Candle fechado
        candle_fechado = df.iloc[-2]
        close_fechado = candle_fechado['close']
        open_fechado = candle_fechado['open']
        ma21_fechado = candle_fechado['ma21']
        candle_atual_data = df['time'].iloc[-1]
        
        # Sinais INVERTIDOS
        sinal_compra = open_fechado > close_fechado and close_fechado < ma21_fechado
        sinal_venda = close_fechado > open_fechado and close_fechado > ma21_fechado
        
        if self.posicao_aberta:
            # Inversão automática
            if self.posicao_aberta['direcao'] == "CALL" and sinal_venda:
                if candle_atual_data != self.ultimo_candle_venda:
                    logger.info(f"📊 EST 8 (HEDGE): INVERSÃO! COMPRA → VENDA")
                    if self.abrir_posicao("PUT"):
                        self.ultimo_candle_venda = candle_atual_data
            
            elif self.posicao_aberta['direcao'] == "PUT" and sinal_compra:
                if candle_atual_data != self.ultimo_candle_compra:
                    logger.info(f"📊 EST 8 (HEDGE): INVERSÃO! VENDA → COMPRA")
                    if self.abrir_posicao("CALL"):
                        self.ultimo_candle_compra = candle_atual_data
        else:
            # Sem posição: abre conforme sinal
            if sinal_compra and candle_atual_data != self.ultimo_candle_compra:
                logger.info(f"📊 EST 8 (HEDGE): COMPRA contra tendência de baixa")
                if self.abrir_posicao("CALL"):
                    self.ultimo_candle_compra = candle_atual_data
            
            elif sinal_venda and candle_atual_data != self.ultimo_candle_venda:
                logger.info(f"📊 EST 8 (HEDGE): VENDA contra tendência de alta")
                if self.abrir_posicao("PUT"):
                    self.ultimo_candle_venda = candle_atual_data
    
    def estrategia_9_candle_ma21_sltp(self, df: pd.DataFrame):
        """
        ESTRATÉGIA 9: CANDLE + MA21 - SAÍDA SL/TP
        Mesma entrada da Estratégia 7, mas SEM inversão automática
        Aguarda apenas SL/TP
        """
        if len(df) < self.ma21_periodo_est9 + 2:
            return
        
        # Se já tem posição, aguarda expiração
        if self.posicao_aberta:
            return
        
        # Calcula MA21
        df['ma21'] = self.calcular_ma(df, self.ma21_periodo_est9, 'EMA')
        
        # Candle fechado
        candle_fechado = df.iloc[-2]
        close_fechado = candle_fechado['close']
        open_fechado = candle_fechado['open']
        ma21_fechado = candle_fechado['ma21']
        candle_atual_data = df['time'].iloc[-1]
        
        # Sinais
        sinal_compra = close_fechado > open_fechado and close_fechado > ma21_fechado
        sinal_venda = open_fechado > close_fechado and close_fechado < ma21_fechado
        
        if sinal_compra and candle_atual_data != self.ultimo_candle_compra:
            logger.info(f"📊 EST 9: COMPRA | Aguarda apenas SL/TP")
            if self.abrir_posicao("CALL"):
                self.ultimo_candle_compra = candle_atual_data
        
        elif sinal_venda and candle_atual_data != self.ultimo_candle_venda:
            logger.info(f"📊 EST 9: VENDA | Aguarda apenas SL/TP")
            if self.abrir_posicao("PUT"):
                self.ultimo_candle_venda = candle_atual_data
    
    def estrategia_10_candle_ma21_invertido_sltp(self, df: pd.DataFrame):
        """
        ESTRATÉGIA 10: CANDLE + MA21 INVERTIDO SL/TP (HEDGE)
        Mesma entrada da Estratégia 8, mas SEM inversão automática
        """
        if len(df) < self.ma21_periodo_est10 + 2:
            return
        
        # Se já tem posição, aguarda expiração
        if self.posicao_aberta:
            return
        
        # Calcula MA21
        df['ma21'] = self.calcular_ma(df, self.ma21_periodo_est10, 'EMA')
        
        # Candle fechado
        candle_fechado = df.iloc[-2]
        close_fechado = candle_fechado['close']
        open_fechado = candle_fechado['open']
        ma21_fechado = candle_fechado['ma21']
        candle_atual_data = df['time'].iloc[-1]
        
        # Sinais INVERTIDOS
        sinal_compra = open_fechado > close_fechado and close_fechado < ma21_fechado
        sinal_venda = close_fechado > open_fechado and close_fechado > ma21_fechado
        
        if sinal_compra and candle_atual_data != self.ultimo_candle_compra:
            logger.info(f"📊 EST 10 (HEDGE): COMPRA | Aguarda apenas SL/TP")
            if self.abrir_posicao("CALL"):
                self.ultimo_candle_compra = candle_atual_data
        
        elif sinal_venda and candle_atual_data != self.ultimo_candle_venda:
            logger.info(f"📊 EST 10 (HEDGE): VENDA | Aguarda apenas SL/TP")
            if self.abrir_posicao("PUT"):
                self.ultimo_candle_venda = candle_atual_data
    
    def estrategia_11_bollinger_bands(self, df: pd.DataFrame):
        """
        ESTRATÉGIA 11: BANDAS DE BOLLINGER - MÚLTIPLAS POSIÇÕES
        COMPRA: Preço atual < Banda Inferior
        VENDA: Preço atual > Banda Superior
        SAÍDA: Retorno à Média ou TP/SL
        Abre múltiplas posições sempre que a condição for satisfeita
        """
        if len(df) < self.bb_periodo + 2:
            return
        
        # Calcula Bandas de Bollinger
        bb_superior, bb_media, bb_inferior = self.calcular_bollinger_bands(
            df, 
            self.bb_periodo, 
            self.bb_desvio
        )
        
        df['bb_superior'] = bb_superior
        df['bb_media'] = bb_media
        df['bb_inferior'] = bb_inferior
        
        # Preço atual (último candle)
        preco_atual = df['close'].iloc[-1]
        bb_sup_atual = df['bb_superior'].iloc[-1]
        bb_med_atual = df['bb_media'].iloc[-1]
        bb_inf_atual = df['bb_inferior'].iloc[-1]
        candle_atual_data = df['time'].iloc[-1]
        
        # Verifica saída se tem posição aberta
        if self.posicao_aberta:
            if self.posicao_aberta['direcao'] == "CALL":
                # Saída COMPRA: Preço atingiu a média
                if preco_atual >= bb_med_atual:
                    logger.info(f"📊 EST 11 (BB): SAÍDA COMPRA - Preço na média | Preço: {preco_atual:.5f} | Média: {bb_med_atual:.5f}")
                    # Na IQ Option, aguarda expiração automática
            
            elif self.posicao_aberta['direcao'] == "PUT":
                # Saída VENDA: Preço atingiu a média
                if preco_atual <= bb_med_atual:
                    logger.info(f"📊 EST 11 (BB): SAÍDA VENDA - Preço na média | Preço: {preco_atual:.5f} | Média: {bb_med_atual:.5f}")
                    # Na IQ Option, aguarda expiração automática
        
        # Sinais de ENTRADA (múltiplas posições permitidas)
        # COMPRA: Preço abaixo da banda inferior
        if preco_atual < bb_inf_atual:
            if candle_atual_data != self.ultimo_candle_compra:
                logger.info(f"📊 EST 11 (BB): COMPRA | Preço: {preco_atual:.5f} < Banda Inf: {bb_inf_atual:.5f}")
                logger.info(f"   Banda Superior: {bb_sup_atual:.5f} | Média: {bb_med_atual:.5f}")
                if self.abrir_posicao("CALL"):
                    self.ultimo_candle_compra = candle_atual_data
        
        # VENDA: Preço acima da banda superior
        elif preco_atual > bb_sup_atual:
            if candle_atual_data != self.ultimo_candle_venda:
                logger.info(f"📊 EST 11 (BB): VENDA | Preço: {preco_atual:.5f} > Banda Sup: {bb_sup_atual:.5f}")
                logger.info(f"   Banda Inferior: {bb_inf_atual:.5f} | Média: {bb_med_atual:.5f}")
                if self.abrir_posicao("PUT"):
                    self.ultimo_candle_venda = candle_atual_data
    
    # =========================================================================
    # LOOP PRINCIPAL
    # =========================================================================
    
    def executar_estrategia(self, df: pd.DataFrame):
        """Executa a estratégia escolhida"""
        estrategias = {
            1: self.estrategia_1_reversao,
            2: self.estrategia_2_acumulacao,
            3: self.estrategia_3_acumulacao_rsi50,
            4: self.estrategia_4_pullback_ma21,
            5: self.estrategia_5_ma_rsi,
            6: self.estrategia_6_ma_rsi_invertido,
            7: self.estrategia_7_candle_ma21,
            8: self.estrategia_8_candle_ma21_invertido,
            9: self.estrategia_9_candle_ma21_sltp,
            10: self.estrategia_10_candle_ma21_invertido_sltp,
            11: self.estrategia_11_bollinger_bands
        }
        
        if self.estrategia_escolhida in estrategias:
            estrategias[self.estrategia_escolhida](df)
        else:
            logger.error(f"❌ Estratégia {self.estrategia_escolhida} inválida!")
    
    def iniciar(self):
        """Inicia o bot"""
        logger.info("🤖 INICIANDO BOT...")
        
        if not self.conectar():
            logger.error("❌ Falha ao conectar. Encerrando...")
            return
        
        try:
            logger.info("🚀 Bot em execução!")
            
            while self.ea_ativo:
                # Verifica horário
                if not self.verificar_horario():
                    logger.info("⏰ Fora do horário de negociação. Aguardando...")
                    time.sleep(60)
                    continue
                
                # Verifica metas
                if self.verificar_metas():
                    self.ea_ativo = False
                    logger.info("🎯 Metas atingidas! Encerrando bot...")
                    break
                
                # Obtém dados
                df = self.obter_candles()
                
                if df is not None and len(df) > 0:
                    # Executa estratégia
                    self.executar_estrategia(df)
                    
                    # Se abriu posição, aguarda resultado
                    if self.posicao_aberta:
                        order_id = self.posicao_aberta['id']
                        self.verificar_resultado_operacao(order_id)
                
                # Aguarda próximo tick (1 segundo)
                time.sleep(1)
        
        except KeyboardInterrupt:
            logger.info("⚠️ Bot interrompido pelo usuário")
        
        except Exception as e:
            logger.error(f"❌ Erro no loop principal: {e}")
        
        finally:
            self.desconectar()
            logger.info("=" * 60)
            logger.info("📊 RESUMO FINAL")
            logger.info("=" * 60)
            logger.info(f"Total de Trades: {self.total_trades}")
            logger.info(f"Trades Vencedores: {self.trades_vencedores}")
            
            if self.total_trades > 0:
                win_rate = self.trades_vencedores / self.total_trades * 100
                logger.info(f"Win Rate: {win_rate:.1f}%")
            
            logger.info(f"Lucro Total: ${self.lucro_total:.2f}")
            logger.info(f"Lucro Diário: ${self.lucro_diario:.2f}")
            logger.info("=" * 60)


# =============================================================================
# EXECUÇÃO
# =============================================================================
if __name__ == "__main__":
    bot = IQOptionPriceActionBot()
    bot.iniciar()
