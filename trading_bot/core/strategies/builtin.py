"""
Estratégias embutidas.

Mudanças conceituais em relação às 11 "estratégias" originais:

  * As versões "invertidas" (6, 8, 10) foram removidas. Inverter um sinal
    ruim não produz um sinal bom — em opções binárias, por causa do payout
    abaixo de 100%, tanto o sinal quanto o seu inverso podem ser perdedores.
    Se A perde dinheiro, não-A também perde. O que existia ali era uma
    duplicação que dobrava a superfície de bug sem valor estatístico.

  * As variantes que só mudavam "saída por SL/TP" vs "inversão" (7/9, 8/10)
    foram unificadas: em opção binária a saída é SEMPRE a expiração. Aqueles
    parâmetros de stop loss em pips não tinham nenhum efeito no código.

  * Toda estratégia agora reporta confiança calibrada, permitindo filtrar
    entradas fracas em vez de operar todo e qualquer cruzamento.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..models import Direction, Signal
from .base import Strategy, register


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(v)))


@register("rsi_reversal")
class RSIReversal(Strategy):
    """Reversão por RSI em zona extrema, com confirmação de exaustão e filtro de ADX."""

    def generate(self, df: pd.DataFrame) -> Signal:
        cur = self.last_closed(df)
        prev = self.previous_closed(df)

        rsi_now, rsi_prev = cur["rsi"], prev["rsi"]
        if pd.isna(rsi_now) or pd.isna(rsi_prev):
            return Signal.none(self.name, "RSI indisponível")

        adx = cur.get("adx", np.nan)
        # Reversão só faz sentido em mercado sem tendência forte.
        if pd.notna(adx) and adx > 35:
            return Signal.none(self.name, f"tendência forte demais para reversão (ADX {adx:.1f})")

        ind = {"rsi": round(float(rsi_now), 2), "adx": round(float(adx), 2) if pd.notna(adx) else 0.0}

        # CALL: RSI saiu da sobrevenda (exaustão vendedora confirmada)
        if rsi_prev <= self.cfg.rsi_oversold < rsi_now:
            depth = (self.cfg.rsi_oversold - min(rsi_prev, self.cfg.rsi_oversold)) / max(self.cfg.rsi_oversold, 1)
            conf = _clamp(0.55 + depth * 0.8 + (0.1 if cur["close"] > cur["open"] else 0.0))
            return Signal(Direction.CALL, conf, self.name,
                          f"RSI cruzou acima de {self.cfg.rsi_oversold} vindo de {rsi_prev:.1f}", ind)

        # PUT: RSI saiu da sobrecompra
        if rsi_prev >= self.cfg.rsi_overbought > rsi_now:
            depth = (max(rsi_prev, self.cfg.rsi_overbought) - self.cfg.rsi_overbought) / max(100 - self.cfg.rsi_overbought, 1)
            conf = _clamp(0.55 + depth * 0.8 + (0.1 if cur["close"] < cur["open"] else 0.0))
            return Signal(Direction.PUT, conf, self.name,
                          f"RSI cruzou abaixo de {self.cfg.rsi_overbought} vindo de {rsi_prev:.1f}", ind)

        return Signal.none(self.name, f"RSI {rsi_now:.1f} fora de zona de sinal")


@register("trend_pullback")
class TrendPullback(Strategy):
    """Segue a tendência comprando recuos à média rápida, com ADX confirmando força."""

    def generate(self, df: pd.DataFrame) -> Signal:
        cur = self.last_closed(df)
        prev = self.previous_closed(df)

        if pd.isna(cur["ma_fast"]) or pd.isna(cur["ma_slow"]) or pd.isna(cur["rsi"]):
            return Signal.none(self.name, "indicadores indisponíveis")

        adx = cur.get("adx", np.nan)
        if pd.isna(adx) or adx < 20:
            return Signal.none(self.name, f"sem tendência definida (ADX {adx:.1f})" if pd.notna(adx) else "ADX indisponível")

        atr = cur.get("atr", np.nan)
        if pd.isna(atr) or atr <= 0:
            return Signal.none(self.name, "ATR indisponível")

        ind = {
            "rsi": round(float(cur["rsi"]), 2),
            "adx": round(float(adx), 2),
            "ma_fast": round(float(cur["ma_fast"]), 6),
            "ma_slow": round(float(cur["ma_slow"]), 6),
        }
        # Distância do preço à média rápida, normalizada por ATR
        dist = abs(cur["close"] - cur["ma_fast"]) / atr
        near_ma = dist <= 0.8
        adx_bonus = _clamp((adx - 20) / 30) * 0.2

        # Tendência de alta: preço acima da lenta, recuo tocando a rápida, candle de retomada
        uptrend = cur["close"] > cur["ma_slow"] and cur["ma_fast"] > cur["ma_slow"]
        if uptrend and near_ma and cur["close"] > cur["open"] and cur["rsi"] > 45:
            conf = _clamp(0.55 + (0.8 - dist) * 0.25 + adx_bonus + (0.05 if prev["close"] < prev["open"] else 0))
            return Signal(Direction.CALL, conf, self.name,
                          f"pullback à MA{self.cfg.ma_fast_period} em tendência de alta (ADX {adx:.1f})", ind)

        downtrend = cur["close"] < cur["ma_slow"] and cur["ma_fast"] < cur["ma_slow"]
        if downtrend and near_ma and cur["close"] < cur["open"] and cur["rsi"] < 55:
            conf = _clamp(0.55 + (0.8 - dist) * 0.25 + adx_bonus + (0.05 if prev["close"] > prev["open"] else 0))
            return Signal(Direction.PUT, conf, self.name,
                          f"pullback à MA{self.cfg.ma_fast_period} em tendência de baixa (ADX {adx:.1f})", ind)

        return Signal.none(self.name, "sem pullback válido")


@register("bollinger_reversion")
class BollingerReversion(Strategy):
    """Reversão à média: rejeição das bandas de Bollinger com confirmação de RSI."""

    def generate(self, df: pd.DataFrame) -> Signal:
        cur = self.last_closed(df)
        prev = self.previous_closed(df)

        if pd.isna(cur["bb_upper"]) or pd.isna(cur["bb_lower"]):
            return Signal.none(self.name, "bandas indisponíveis")

        adx = cur.get("adx", np.nan)
        if pd.notna(adx) and adx > 35:
            return Signal.none(self.name, f"tendência forte demais (ADX {adx:.1f})")

        pct_b = cur.get("bb_percent_b", np.nan)
        ind = {
            "bb_percent_b": round(float(pct_b), 3) if pd.notna(pct_b) else 0.0,
            "rsi": round(float(cur["rsi"]), 2) if pd.notna(cur["rsi"]) else 0.0,
        }

        # CALL: candle anterior perfurou a banda inferior e o atual fechou de volta para dentro
        pierced_low = prev["low"] < prev["bb_lower"]
        back_inside_up = cur["close"] > cur["bb_lower"] and cur["close"] > cur["open"]
        if pierced_low and back_inside_up and cur["rsi"] < 45:
            conf = _clamp(0.58 + (45 - cur["rsi"]) / 100 + (0.1 if cur["close"] > prev["high"] else 0))
            return Signal(Direction.CALL, conf, self.name,
                          "rejeição da banda inferior com retorno para dentro", ind)

        pierced_high = prev["high"] > prev["bb_upper"]
        back_inside_down = cur["close"] < cur["bb_upper"] and cur["close"] < cur["open"]
        if pierced_high and back_inside_down and cur["rsi"] > 55:
            conf = _clamp(0.58 + (cur["rsi"] - 55) / 100 + (0.1 if cur["close"] < prev["low"] else 0))
            return Signal(Direction.PUT, conf, self.name,
                          "rejeição da banda superior com retorno para dentro", ind)

        return Signal.none(self.name, "sem rejeição de banda")


@register("macd_momentum")
class MACDMomentum(Strategy):
    """Cruzamento do MACD alinhado à tendência da média lenta."""

    def generate(self, df: pd.DataFrame) -> Signal:
        cur = self.last_closed(df)
        prev = self.previous_closed(df)

        if pd.isna(cur["macd"]) or pd.isna(cur["macd_signal"]):
            return Signal.none(self.name, "MACD indisponível")

        ind = {
            "macd": round(float(cur["macd"]), 6),
            "macd_signal": round(float(cur["macd_signal"]), 6),
            "macd_hist": round(float(cur["macd_hist"]), 6),
        }
        # Normaliza a força do histograma pelo ATR para comparar entre ativos
        atr = cur.get("atr", np.nan)
        strength = _clamp(abs(cur["macd_hist"]) / atr) * 0.3 if pd.notna(atr) and atr > 0 else 0.0

        crossed_up = prev["macd"] <= prev["macd_signal"] and cur["macd"] > cur["macd_signal"]
        if crossed_up and self.trend_ok(cur, Direction.CALL):
            return Signal(Direction.CALL, _clamp(0.58 + strength), self.name,
                          "MACD cruzou a linha de sinal para cima", ind)

        crossed_down = prev["macd"] >= prev["macd_signal"] and cur["macd"] < cur["macd_signal"]
        if crossed_down and self.trend_ok(cur, Direction.PUT):
            return Signal(Direction.PUT, _clamp(0.58 + strength), self.name,
                          "MACD cruzou a linha de sinal para baixo", ind)

        return Signal.none(self.name, "sem cruzamento de MACD")


@register("confluence")
class Confluence(Strategy):
    """Votação ponderada de RSI, MACD, Bollinger, tendência e ADX — a mais seletiva."""

    def generate(self, df: pd.DataFrame) -> Signal:
        cur = self.last_closed(df)
        prev = self.previous_closed(df)

        needed = ["rsi", "macd", "macd_signal", "ma_fast", "ma_slow", "bb_percent_b"]
        if any(pd.isna(cur.get(c, np.nan)) for c in needed):
            return Signal.none(self.name, "indicadores ainda estabilizando")

        votes: list[tuple[Direction, float, str]] = []

        # 1. RSI saindo de extremo
        if prev["rsi"] <= self.cfg.rsi_oversold < cur["rsi"]:
            votes.append((Direction.CALL, 1.0, "RSI saiu da sobrevenda"))
        elif prev["rsi"] >= self.cfg.rsi_overbought > cur["rsi"]:
            votes.append((Direction.PUT, 1.0, "RSI saiu da sobrecompra"))
        elif cur["rsi"] > 55:
            votes.append((Direction.CALL, 0.4, "RSI com viés comprador"))
        elif cur["rsi"] < 45:
            votes.append((Direction.PUT, 0.4, "RSI com viés vendedor"))

        # 2. MACD
        if cur["macd"] > cur["macd_signal"]:
            w = 1.0 if prev["macd"] <= prev["macd_signal"] else 0.5
            votes.append((Direction.CALL, w, "MACD comprador"))
        else:
            w = 1.0 if prev["macd"] >= prev["macd_signal"] else 0.5
            votes.append((Direction.PUT, w, "MACD vendedor"))

        # 3. Posição nas bandas
        pb = cur["bb_percent_b"]
        if pb < 0.15:
            votes.append((Direction.CALL, 0.8, "preço na banda inferior"))
        elif pb > 0.85:
            votes.append((Direction.PUT, 0.8, "preço na banda superior"))

        # 4. Estrutura de tendência
        if cur["ma_fast"] > cur["ma_slow"] and cur["close"] > cur["ma_fast"]:
            votes.append((Direction.CALL, 0.7, "estrutura de alta"))
        elif cur["ma_fast"] < cur["ma_slow"] and cur["close"] < cur["ma_fast"]:
            votes.append((Direction.PUT, 0.7, "estrutura de baixa"))

        # 5. Cor do candle fechado
        votes.append((Direction.CALL if cur["close"] > cur["open"] else Direction.PUT, 0.3, "candle"))

        call_w = sum(w for d, w, _ in votes if d is Direction.CALL)
        put_w = sum(w for d, w, _ in votes if d is Direction.PUT)
        total = call_w + put_w
        if total == 0:
            return Signal.none(self.name, "sem votos")

        direction = Direction.CALL if call_w > put_w else Direction.PUT
        agreement = max(call_w, put_w) / total

        # Exige maioria qualificada: 65% do peso na mesma direção
        if agreement < 0.65:
            return Signal.none(self.name, f"confluência insuficiente ({agreement:.0%})")

        adx = cur.get("adx", np.nan)
        adx_bonus = _clamp((adx - 20) / 40) * 0.1 if pd.notna(adx) else 0.0
        conf = _clamp(agreement * 0.9 + adx_bonus)

        reasons = "; ".join(r for d, _, r in votes if d is direction)
        ind = {
            "rsi": round(float(cur["rsi"]), 2),
            "macd_hist": round(float(cur["macd_hist"]), 6),
            "bb_percent_b": round(float(pb), 3),
            "adx": round(float(adx), 2) if pd.notna(adx) else 0.0,
            "agreement": round(agreement, 3),
        }
        return Signal(direction, conf, self.name, f"confluência {agreement:.0%}: {reasons}", ind)
