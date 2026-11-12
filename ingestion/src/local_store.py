"""Armazenamento local do dado bruto, no mesmo layout que o bucket do GCS terá na Fase 2.

<raiz>/bcb/serie=<codigo>/ingestion_date=AAAA-MM-DD/dados.json
"""

import json
from datetime import date
from pathlib import Path

from src.extract import Registro, parse_data


def caminho_particao(raiz: Path, codigo: int, ingestion_date: date) -> Path:
    return (
        raiz
        / "bcb"
        / f"serie={codigo}"
        / f"ingestion_date={ingestion_date.isoformat()}"
        / "dados.json"
    )


def salvar_bruto(raiz: Path, codigo: int, ingestion_date: date, registros: list[Registro]) -> Path:
    """Grava (ou sobrescreve) a partição do dia. Sobrescrever é o que torna a carga idempotente."""
    caminho = caminho_particao(raiz, codigo, ingestion_date)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(registros, ensure_ascii=False), encoding="utf-8")
    return caminho


def ultima_data_carregada(raiz: Path, codigo: int, antes_de: date) -> date | None:
    """Maior data já carregada, olhando só partições anteriores a `antes_de`.

    A partição de hoje fica de fora de propósito: assim, rodar de novo no mesmo dia
    refaz o mesmo pedido e sobrescreve a mesma partição, em vez de gerar um arquivo
    só com a diferença.
    """
    pasta_serie = raiz / "bcb" / f"serie={codigo}"
    maior: date | None = None
    for arquivo in pasta_serie.glob("ingestion_date=*/dados.json"):
        ingestion_date = date.fromisoformat(arquivo.parent.name.split("=", 1)[1])
        if ingestion_date >= antes_de:
            continue
        for registro in json.loads(arquivo.read_text(encoding="utf-8")):
            data_registro = parse_data(registro["data"])
            if maior is None or data_registro > maior:
                maior = data_registro
    return maior
