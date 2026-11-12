import json
from datetime import date
from pathlib import Path

import responses

from src import config
from src.config import Serie
from src.local_store import caminho_particao, salvar_bruto, ultima_data_carregada
from src.main import executar

IPCA = Serie(codigo=433, nome="ipca_mensal", periodicidade="mensal")
IGPM = Serie(codigo=189, nome="igpm_mensal", periodicidade="mensal")
URL_433 = config.URL_API_SGS.format(codigo=433)
URL_189 = config.URL_API_SGS.format(codigo=189)


def test_caminho_particao_segue_o_layout_hive(tmp_path: Path) -> None:
    caminho = caminho_particao(tmp_path, 433, date(2024, 6, 15))
    assert caminho == tmp_path / "bcb" / "serie=433" / "ingestion_date=2024-06-15" / "dados.json"


def test_ultima_data_carregada_sem_arquivos_e_none(tmp_path: Path) -> None:
    assert ultima_data_carregada(tmp_path, 433, antes_de=date(2024, 6, 15)) is None


def test_ultima_data_carregada_ignora_a_particao_de_hoje(tmp_path: Path) -> None:
    salvar_bruto(tmp_path, 433, date(2024, 6, 14), [{"data": "01/05/2024", "valor": "0.46"}])
    salvar_bruto(tmp_path, 433, date(2024, 6, 15), [{"data": "01/06/2024", "valor": "0.21"}])

    assert ultima_data_carregada(tmp_path, 433, antes_de=date(2024, 6, 15)) == date(2024, 5, 1)
    assert ultima_data_carregada(tmp_path, 433, antes_de=date(2024, 6, 16)) == date(2024, 6, 1)


@responses.activate
def test_executar_duas_vezes_no_mesmo_dia_da_o_mesmo_resultado(tmp_path: Path) -> None:
    salvar_bruto(tmp_path, 433, date(2024, 6, 14), [{"data": "01/05/2024", "valor": "0.46"}])
    responses.get(URL_433, json=[{"data": "01/06/2024", "valor": "0.21"}])
    hoje = date(2024, 6, 15)

    assert executar(tmp_path, hoje, series=(IPCA,)) == 0
    arquivo = caminho_particao(tmp_path, 433, hoje)
    primeira = arquivo.read_text(encoding="utf-8")
    assert executar(tmp_path, hoje, series=(IPCA,)) == 0

    assert arquivo.read_text(encoding="utf-8") == primeira
    assert json.loads(primeira) == [{"data": "01/06/2024", "valor": "0.21"}]
    assert responses.calls[1].request.params["dataInicial"] == "02/05/2024"


@responses.activate
def test_executar_falha_em_uma_serie_nao_impede_as_outras(tmp_path: Path) -> None:
    salvar_bruto(tmp_path, 433, date(2024, 6, 14), [{"data": "01/05/2024", "valor": "0.46"}])
    salvar_bruto(tmp_path, 189, date(2024, 6, 14), [{"data": "01/05/2024", "valor": "0.89"}])
    responses.get(URL_433, status=400)
    responses.get(URL_189, json=[{"data": "01/06/2024", "valor": "0.81"}])
    hoje = date(2024, 6, 15)

    assert executar(tmp_path, hoje, series=(IPCA, IGPM)) == 1

    assert not caminho_particao(tmp_path, 433, hoje).exists()
    assert caminho_particao(tmp_path, 189, hoje).exists()
