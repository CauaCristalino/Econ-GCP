"""Ponto de entrada da ingestão local: python -m src.main (a partir da pasta ingestion/)."""

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

import requests

from src import config
from src.extract import ExtractError, extrair_serie
from src.local_store import salvar_bruto, ultima_data_carregada
from src.logging_config import configurar_logging

logger = logging.getLogger(__name__)


def executar(raiz: Path, hoje: date, series: tuple[config.Serie, ...] = config.SERIES) -> int:
    """Extrai cada série e grava o bruto. Devolve quantas séries falharam."""
    falhas = 0
    with requests.Session() as session:
        for serie in series:
            try:
                ultima = ultima_data_carregada(raiz, serie.codigo, antes_de=hoje)
                registros = extrair_serie(session, serie, ultima, hoje)
            except ExtractError:
                # Uma série fora do ar não deve impedir as outras de carregar.
                logger.exception("falha ao extrair série", extra={"serie": serie.codigo})
                falhas += 1
                continue
            if registros:
                caminho = salvar_bruto(raiz, serie.codigo, hoje, registros)
                logger.info("bruto gravado", extra={"serie": serie.codigo, "caminho": str(caminho)})
    return falhas


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingestão das séries do BCB (SGS).")
    parser.add_argument("--saida", type=Path, default=Path("data/raw"), help="pasta do dado bruto")
    args = parser.parse_args()

    configurar_logging()
    falhas = executar(args.saida, date.today())
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
