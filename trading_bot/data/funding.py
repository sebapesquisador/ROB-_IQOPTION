"""
Histórico de funding rate dos contratos perpétuos da Binance.

Por que este dado e não outro indicador
---------------------------------------
As cinco estratégias testadas até aqui liam apenas o preço, e todas
empataram com entradas sorteadas. A razão é estrutural: RSI, MACD e
Bollinger são funções públicas do mesmo histórico que todo mundo enxerga.
Se previssem o próximo movimento, a previsão já estaria no preço.

O funding rate é diferente em espécie. Ele não é calculado a partir do
preço — é um **pagamento real entre participantes**, a cada 8 horas, que
existe para manter o perpétuo colado no spot. Quando está positivo, quem
está comprado paga a quem está vendido; quando negativo, o contrário.

Isso o torna uma medida direta de **posicionamento e de custo de carrego**,
não de histórico de cotação. É informação sobre quem está do outro lado, e
não sobre onde o preço esteve. Pode não prever nada — a hipótese precisa
ser testada com o mesmo rigor das anteriores — mas ao menos não é
tautológica.

Endpoint público, sem chave de API:
https://fapi.binance.com/fapi/v1/fundingRate
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

logger = logging.getLogger(__name__)

_URL_FUNDING = "https://fapi.binance.com/fapi/v1/fundingRate"
_MAX_POR_REQUISICAO = 1000        # teto da API
_TENTATIVAS = 3

# O funding é liquidado a cada 8 horas: 00:00, 08:00 e 16:00 UTC.
HORAS_ENTRE_PAGAMENTOS = 8
PAGAMENTOS_POR_ANO = 365 * 24 / HORAS_ENTRE_PAGAMENTOS      # 1095


class FundingError(RuntimeError):
    """Falha ao obter ou interpretar o histórico de funding."""


def _requisitar(symbol: str, limite: int, fim_ms: int | None) -> list:
    params = {"symbol": symbol.upper(), "limit": limite}
    if fim_ms is not None:
        params["endTime"] = fim_ms
    url = f"{_URL_FUNDING}?{urllib.parse.urlencode(params)}"

    ultimo: Exception | None = None
    for tentativa in range(1, _TENTATIVAS + 1):
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            corpo = exc.read().decode("utf-8", "replace")[:200]
            if exc.code == 400:
                raise FundingError(
                    f"A Binance recusou o símbolo '{symbol}' no mercado de "
                    f"perpétuos. Nem todo par spot tem perpétuo; tente "
                    f"BTCUSDT ou ETHUSDT. ({corpo})"
                ) from exc
            ultimo = exc
        except Exception as exc:
            ultimo = exc
        if tentativa < _TENTATIVAS:
            time.sleep(tentativa)
    raise FundingError(f"Falha ao obter funding de {symbol}: {ultimo}")


def baixar_funding(symbol: str, count: int = 1000) -> pd.DataFrame:
    """Baixa os `count` pagamentos de funding mais recentes.

    Pagina para trás, como o adaptador de candles: pedir mais que o teto da
    API e receber só 1000 em silêncio já nos custou análises erradas duas
    vezes neste projeto.

    Devolve colunas `timestamp` (UTC) e `rate` (fração por período, não
    percentual: 0,0001 = 0,01%).
    """
    if count <= 0:
        return pd.DataFrame(columns=["timestamp", "rate"])

    paginas: list[list] = []
    restante = count
    fim_ms: int | None = None
    mais_antigo_visto: int | None = None

    while restante > 0:
        lote = _requisitar(symbol, min(restante, _MAX_POR_REQUISICAO), fim_ms)
        if not lote:
            break

        paginas.append(lote)
        restante -= len(lote)

        mais_antigo = int(lote[0]["fundingTime"])
        if mais_antigo_visto is not None and mais_antigo >= mais_antigo_visto:
            break                      # a API parou de retroceder
        mais_antigo_visto = mais_antigo
        fim_ms = mais_antigo - 1

        if len(lote) < _MAX_POR_REQUISICAO:
            break                      # fim do histórico disponível

    registros = [item for pagina in paginas for item in pagina]
    if not registros:
        raise FundingError(
            f"A Binance não devolveu nenhum funding para {symbol}."
        )

    df = pd.DataFrame({
        "timestamp": pd.to_datetime(
            [int(r["fundingTime"]) for r in registros], unit="ms", utc=True),
        "rate": [float(r["fundingRate"]) for r in registros],
    })
    df = df.drop_duplicates(subset="timestamp").sort_values("timestamp")
    df = df.reset_index(drop=True)

    if len(df) < count:
        logger.info("histórico de funding de %s tem %d registros (pedidos %d)",
                    symbol, len(df), count)
    return df.tail(count).reset_index(drop=True)


def rendimento_carry(funding: pd.DataFrame) -> dict:
    """Quanto renderia receber o funding, sem apostar em direção.

    Vender o perpétuo e comprar o spot na mesma quantidade deixa a posição
    neutra em preço: o que sobe de um lado desce do outro. O que resta é o
    funding, pago a cada 8 horas por quem está comprado.

    Isto NÃO é previsão — é uma taxa observada. Por isso vale reportar
    separado de qualquer teste de sinal: a conta é aritmética, não
    estatística. Os riscos são outros (liquidação, corretora, execução), e
    nenhum deles aparece aqui.
    """
    if funding is None or funding.empty:
        return {}

    taxas = funding["rate"].astype(float)
    media = float(taxas.mean())
    periodos = len(taxas)
    dias = periodos * HORAS_ENTRE_PAGAMENTOS / 24

    return {
        "periodos": periodos,
        "dias": round(dias, 1),
        "media_por_periodo_pct": round(media * 100, 5),
        "acumulado_pct": round(float(taxas.sum()) * 100, 2),
        "anualizado_pct": round(media * PAGAMENTOS_POR_ANO * 100, 2),
        "positivos_pct": round(float((taxas > 0).mean()) * 100, 1),
        "maior_pct": round(float(taxas.max()) * 100, 4),
        "menor_pct": round(float(taxas.min()) * 100, 4),
    }
