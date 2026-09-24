"""
O funding rate prevê o retorno seguinte do spot?

A hipótese
----------
Funding muito positivo significa que há mais gente comprada pagando para
manter a posição — posicionamento esticado para um lado. A leitura
contrária diz que esse excesso costuma se desfazer, e que o preço tende a
cair depois. Funding negativo diria o oposto.

É uma hipótese plausível e muito repetida. Este módulo existe para
verificá-la, não para confirmá-la.

Como o teste é montado
----------------------
Para cada pagamento de funding em t, mede-se o retorno do spot de t até
t+H. Depois se compara o retorno médio do quintil de funding mais alto
contra o do mais baixo.

A significância vem de um **teste de permutação**: embaralha-se qual
retorno pertence a qual funding, milhares de vezes, e mede-se com que
frequência o acaso produz uma diferença tão grande quanto a observada. É o
mesmo espírito da referência aleatória usada no backtester — comparar
contra o que o nada produz — mas sem supor distribuição nenhuma.

Os retornos se sobrepõem quando H > 8h (duas janelas consecutivas
compartilham horas), o que infla a confiança de testes clássicos. O
permutation test sofre menos com isso, e o relatório avisa quando há
sobreposição.
"""
from __future__ import annotations

import logging
import random
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

HORAS_ENTRE_PAGAMENTOS = 8


def alinhar(funding: pd.DataFrame, candles: pd.DataFrame,
            horizonte_horas: int = 8) -> pd.DataFrame:
    """Casa cada funding com o retorno do spot no período seguinte.

    A entrada é sempre no candle **posterior** ao horário do funding: no
    instante exato do pagamento a informação ainda não está disponível para
    quem operaria depois dele. Usar o próprio candle seria olhar o futuro —
    o mesmo erro de look-ahead que a auditoria encontrou no código antigo.
    """
    if funding is None or funding.empty or candles is None or candles.empty:
        return pd.DataFrame(columns=["timestamp", "rate", "retorno_pct"])

    velas = candles.copy()
    velas["timestamp"] = pd.to_datetime(velas["timestamp"], utc=True)
    velas = velas.sort_values("timestamp").reset_index(drop=True)
    tempos = velas["timestamp"]

    horizonte = pd.Timedelta(hours=horizonte_horas)
    linhas = []

    for _, evento in funding.iterrows():
        t0 = pd.Timestamp(evento["timestamp"])
        if t0.tzinfo is None:
            t0 = t0.tz_localize("utc")

        # searchsorted com 'right': o primeiro candle que ABRE depois do
        # pagamento. Nunca o candle que contém o instante do pagamento.
        i_entrada = int(tempos.searchsorted(t0, side="right"))
        if i_entrada >= len(velas):
            continue

        # O horizonte conta a partir da ENTRADA, não do pagamento. Medir do
        # pagamento encurtaria a janela justamente pelo atraso que impusemos
        # para não olhar o futuro — o custo da precaução viraria ruído nos
        # dados.
        limite = tempos.iloc[i_entrada] + horizonte
        i_saida = int(tempos.searchsorted(limite, side="left")) - 1
        if i_saida <= i_entrada:
            continue

        entrada = float(velas["open"].iloc[i_entrada])
        saida = float(velas["close"].iloc[i_saida])
        if entrada <= 0:
            continue

        linhas.append({
            "timestamp": t0,
            "rate": float(evento["rate"]),
            "retorno_pct": (saida / entrada - 1.0) * 100.0,
        })

    return pd.DataFrame(linhas)


def por_quantil(dados: pd.DataFrame, n_grupos: int = 5) -> list[dict]:
    """Retorno médio do spot em cada faixa de funding.

    Se a hipótese tiver fundo, os grupos devem se ordenar: funding alto com
    retorno pior, funding baixo com retorno melhor. Uma diferença que
    aparece só nos extremos, sem ordem no meio, costuma ser ruído.
    """
    if dados is None or len(dados) < n_grupos * 2:
        return []

    df = dados.copy()
    try:
        df["grupo"] = pd.qcut(df["rate"], n_grupos, labels=False,
                              duplicates="drop")
    except ValueError:
        return []

    saida = []
    for g in sorted(df["grupo"].dropna().unique()):
        fatia = df[df["grupo"] == g]
        saida.append({
            "grupo": int(g) + 1,
            "n": len(fatia),
            "funding_medio_pct": round(float(fatia["rate"].mean()) * 100, 5),
            "retorno_medio_pct": round(float(fatia["retorno_pct"].mean()), 4),
            "acerto_alta_pct": round(float((fatia["retorno_pct"] > 0).mean()) * 100, 1),
        })
    return saida


def _spread(dados: pd.DataFrame, n_grupos: int) -> Optional[float]:
    """Retorno do quintil de funding mais baixo menos o do mais alto.

    Positivo é o que a hipótese contrária prevê: funding baixo rendendo
    mais que funding alto.
    """
    grupos = por_quantil(dados, n_grupos)
    if len(grupos) < 2:
        return None
    return grupos[0]["retorno_medio_pct"] - grupos[-1]["retorno_medio_pct"]


def teste_permutacao(dados: pd.DataFrame, n_grupos: int = 5,
                     permutacoes: int = 5000, seed: int = 0) -> dict:
    """Com que frequência o acaso produz um spread deste tamanho?

    Embaralhar os retornos destrói qualquer relação com o funding, mas
    preserva a distribuição dos retornos — inclusive caudas gordas e
    volatilidade agrupada, que enganam testes que supõem normalidade.
    """
    if dados is None or len(dados) < n_grupos * 4:
        return {}

    observado = _spread(dados, n_grupos)
    if observado is None:
        return {}

    rng = random.Random(seed)
    embaralhado = dados.copy()
    retornos = list(dados["retorno_pct"])
    extremos = 0

    for _ in range(permutacoes):
        rng.shuffle(retornos)
        embaralhado["retorno_pct"] = retornos
        s = _spread(embaralhado, n_grupos)
        if s is not None and abs(s) >= abs(observado):
            extremos += 1

    # +1 no numerador e no denominador: com 0 ocorrências o p não é zero,
    # é "menor que 1/permutações". Fingir zero seria exagerar a certeza.
    p = (extremos + 1) / (permutacoes + 1)
    return {
        "spread_pct": round(observado, 4),
        "p_value": round(p, 4),
        "permutacoes": permutacoes,
        "n": len(dados),
    }


def dividir(dados: pd.DataFrame, fracao_teste: float = 0.3):
    """Separa um pedaço final que não participa de escolha nenhuma.

    A lição mais cara do projeto: escolher e avaliar nos mesmos dados
    inflou uma vantagem inexistente em 9 pontos percentuais.
    """
    if dados is None or dados.empty:
        return dados, dados
    corte = int(len(dados) * (1 - fracao_teste))
    return dados.iloc[:corte].copy(), dados.iloc[corte:].copy()
