"""Configuração da ingestão: quais séries buscar e os parâmetros da API SGS do BCB."""

from dataclasses import dataclass
from datetime import date

# {codigo} é o código da série no SGS. A API é pública e não exige chave.
URL_API_SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"

# Primeiro dia pedido na carga histórica (quando ainda não há nada carregado).
INICIO_HISTORICO = date(2000, 1, 1)

# A API limita o período de séries diárias a 10 anos por requisição.
# 3650 dias fica logo abaixo desse teto, então a carga histórica é feita em janelas.
JANELA_MAX_DIAS = 3650

TIMEOUT_SEGUNDOS = 30
MAX_TENTATIVAS = 4
BACKOFF_BASE_SEGUNDOS = 2.0  # esperas de 2s, 4s, 8s entre as tentativas


@dataclass(frozen=True)
class Serie:
    codigo: int
    nome: str
    periodicidade: str  # "diaria" ou "mensal"


# Confirme cada código no portal SGS (https://www3.bcb.gov.br/sgspub) antes de usar.
SERIES: tuple[Serie, ...] = (
    Serie(codigo=432, nome="selic_meta", periodicidade="diaria"),
    Serie(codigo=433, nome="ipca_mensal", periodicidade="mensal"),
    Serie(codigo=1, nome="dolar_comercial_venda", periodicidade="diaria"),
    Serie(codigo=189, nome="igpm_mensal", periodicidade="mensal"),
)
