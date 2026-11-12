"""Extração das séries temporais da API SGS do Banco Central, com retry e carga incremental."""

import logging
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import TypedDict

import requests

from src import config
from src.config import Serie

logger = logging.getLogger(__name__)

FORMATO_DATA_API = "%d/%m/%Y"

# Falhas passageiras: vale a pena tentar de novo. Um 400, por exemplo, não muda se repetir.
STATUS_COM_RETRY = frozenset({429, 500, 502, 503, 504})


class Registro(TypedDict):
    """Um ponto da série, exatamente como a API devolve (tudo texto)."""

    data: str  # dd/MM/aaaa
    valor: str


class ExtractError(Exception):
    """A API respondeu algo inesperado ou as tentativas se esgotaram."""


def gerar_janelas(inicio: date, fim: date, max_dias: int) -> list[tuple[date, date]]:
    """Divide [inicio, fim] em janelas consecutivas de no máximo `max_dias` dias."""
    janelas: list[tuple[date, date]] = []
    atual = inicio
    while atual <= fim:
        fim_janela = min(atual + timedelta(days=max_dias - 1), fim)
        janelas.append((atual, fim_janela))
        atual = fim_janela + timedelta(days=1)
    return janelas


def calcular_inicio(ultima_data: date | None, inicio_historico: date) -> date:
    """Carga incremental: começa no dia seguinte ao último já carregado."""
    if ultima_data is None:
        return inicio_historico
    return ultima_data + timedelta(days=1)


def parse_data(texto: str) -> date:
    return datetime.strptime(texto, FORMATO_DATA_API).date()


def buscar_janela(
    session: requests.Session,
    codigo: int,
    inicio: date,
    fim: date,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> list[Registro]:
    """Busca uma janela da série, repetindo com backoff exponencial em falhas passageiras."""
    url = config.URL_API_SGS.format(codigo=codigo)
    params = {
        "formato": "json",
        "dataInicial": inicio.strftime(FORMATO_DATA_API),
        "dataFinal": fim.strftime(FORMATO_DATA_API),
    }
    ultimo_erro = ""

    for tentativa in range(1, config.MAX_TENTATIVAS + 1):
        try:
            resposta = session.get(url, params=params, timeout=config.TIMEOUT_SEGUNDOS)
        except (requests.ConnectionError, requests.Timeout) as erro:
            ultimo_erro = repr(erro)
        else:
            if resposta.status_code == 200:
                return _validar_corpo(resposta, codigo)
            if resposta.status_code == 404:
                # A API responde 404 quando não há valores no período pedido.
                logger.warning(
                    "sem dados no período",
                    extra={"serie": codigo, "inicio": str(inicio), "fim": str(fim)},
                )
                return []
            if resposta.status_code not in STATUS_COM_RETRY:
                raise ExtractError(
                    f"série {codigo}: HTTP {resposta.status_code} — {resposta.text[:200]}"
                )
            ultimo_erro = f"HTTP {resposta.status_code}"

        if tentativa < config.MAX_TENTATIVAS:
            espera = config.BACKOFF_BASE_SEGUNDOS * 2 ** (tentativa - 1)
            logger.warning(
                "falha passageira, nova tentativa",
                extra={
                    "serie": codigo,
                    "tentativa": tentativa,
                    "espera_s": espera,
                    "erro": ultimo_erro,
                },
            )
            sleep(espera)

    raise ExtractError(
        f"série {codigo}: {config.MAX_TENTATIVAS} tentativas esgotadas ({ultimo_erro})"
    )


def _validar_corpo(resposta: requests.Response, codigo: int) -> list[Registro]:
    try:
        corpo = resposta.json()
    except ValueError as erro:
        raise ExtractError(f"série {codigo}: resposta não é JSON") from erro
    if not isinstance(corpo, list):
        raise ExtractError(f"série {codigo}: esperava uma lista, veio {type(corpo).__name__}")

    registros: list[Registro] = []
    for item in corpo:
        if not isinstance(item, dict) or "data" not in item or "valor" not in item:
            raise ExtractError(f"série {codigo}: registro fora do formato esperado: {item!r}")
        registros.append({"data": str(item["data"]), "valor": str(item["valor"])})
    return registros


def extrair_serie(
    session: requests.Session,
    serie: Serie,
    ultima_data: date | None,
    hoje: date,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> list[Registro]:
    """Extrai só o período novo da série: do dia seguinte a `ultima_data` até `hoje`."""
    inicio = calcular_inicio(ultima_data, config.INICIO_HISTORICO)
    if inicio > hoje:
        logger.info("série já está em dia", extra={"serie": serie.codigo})
        return []

    registros: list[Registro] = []
    for inicio_janela, fim_janela in gerar_janelas(inicio, hoje, config.JANELA_MAX_DIAS):
        registros.extend(
            buscar_janela(session, serie.codigo, inicio_janela, fim_janela, sleep=sleep)
        )

    # Descarta qualquer ponto fora do período pedido, para nunca recarregar dado antigo.
    novos = [r for r in registros if inicio <= parse_data(r["data"]) <= hoje]
    logger.info(
        "série extraída",
        extra={
            "serie": serie.codigo,
            "nome": serie.nome,
            "inicio": str(inicio),
            "fim": str(hoje),
            "registros": len(novos),
        },
    )
    return novos
