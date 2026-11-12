from datetime import date

import pytest
import requests
import responses

from src import config
from src.config import Serie
from src.extract import (
    ExtractError,
    buscar_janela,
    calcular_inicio,
    extrair_serie,
    gerar_janelas,
)

URL_433 = config.URL_API_SGS.format(codigo=433)
IPCA = Serie(codigo=433, nome="ipca_mensal", periodicidade="mensal")


class SleepFalso:
    """Substitui time.sleep: registra as esperas sem deixar o teste lento."""

    def __init__(self) -> None:
        self.esperas: list[float] = []

    def __call__(self, segundos: float) -> None:
        self.esperas.append(segundos)


def test_gerar_janelas_periodo_cabe_em_uma_janela() -> None:
    assert gerar_janelas(date(2024, 1, 1), date(2024, 1, 31), 3650) == [
        (date(2024, 1, 1), date(2024, 1, 31))
    ]


def test_gerar_janelas_divide_sem_buracos_nem_sobreposicao() -> None:
    janelas = gerar_janelas(date(2024, 1, 1), date(2024, 1, 25), 10)
    assert janelas == [
        (date(2024, 1, 1), date(2024, 1, 10)),
        (date(2024, 1, 11), date(2024, 1, 20)),
        (date(2024, 1, 21), date(2024, 1, 25)),
    ]


def test_gerar_janelas_inicio_depois_do_fim_e_vazio() -> None:
    assert gerar_janelas(date(2024, 2, 1), date(2024, 1, 1), 10) == []


def test_calcular_inicio_sem_carga_anterior_usa_o_historico() -> None:
    assert calcular_inicio(None, date(2000, 1, 1)) == date(2000, 1, 1)


def test_calcular_inicio_incremental_e_o_dia_seguinte() -> None:
    assert calcular_inicio(date(2024, 5, 31), date(2000, 1, 1)) == date(2024, 6, 1)


@responses.activate
def test_buscar_janela_envia_datas_no_formato_da_api() -> None:
    responses.get(URL_433, json=[{"data": "01/01/2024", "valor": "0.42"}])

    registros = buscar_janela(requests.Session(), 433, date(2024, 1, 1), date(2024, 1, 31))

    assert registros == [{"data": "01/01/2024", "valor": "0.42"}]
    params = responses.calls[0].request.params
    assert params == {"formato": "json", "dataInicial": "01/01/2024", "dataFinal": "31/01/2024"}


@responses.activate
def test_buscar_janela_repete_apos_erro_passageiro_com_backoff() -> None:
    responses.get(URL_433, status=503)
    responses.get(URL_433, body=requests.ConnectionError("caiu"))
    responses.get(URL_433, json=[{"data": "01/01/2024", "valor": "0.42"}])
    sleep = SleepFalso()

    registros = buscar_janela(
        requests.Session(), 433, date(2024, 1, 1), date(2024, 1, 31), sleep=sleep
    )

    assert len(registros) == 1
    assert len(responses.calls) == 3
    assert sleep.esperas == [2.0, 4.0]


@responses.activate
def test_buscar_janela_desiste_depois_do_maximo_de_tentativas() -> None:
    responses.get(URL_433, status=500)
    sleep = SleepFalso()

    with pytest.raises(ExtractError, match="tentativas esgotadas"):
        buscar_janela(requests.Session(), 433, date(2024, 1, 1), date(2024, 1, 31), sleep=sleep)

    assert len(responses.calls) == config.MAX_TENTATIVAS
    assert sleep.esperas == [2.0, 4.0, 8.0]


@responses.activate
def test_buscar_janela_nao_repete_erro_do_cliente() -> None:
    responses.get(URL_433, status=400, body="parametro invalido")
    sleep = SleepFalso()

    with pytest.raises(ExtractError, match="HTTP 400"):
        buscar_janela(requests.Session(), 433, date(2024, 1, 1), date(2024, 1, 31), sleep=sleep)

    assert len(responses.calls) == 1
    assert sleep.esperas == []


@responses.activate
def test_buscar_janela_404_significa_periodo_sem_dados() -> None:
    responses.get(URL_433, status=404, json={"error": "Value(s) not found"})

    assert buscar_janela(requests.Session(), 433, date(2024, 1, 1), date(2024, 1, 31)) == []


@responses.activate
@pytest.mark.parametrize(
    "corpo",
    [{"erro": "x"}, [{"data": "01/01/2024"}], ["texto"]],
)
def test_buscar_janela_rejeita_corpo_fora_do_formato(corpo: object) -> None:
    responses.get(URL_433, json=corpo)

    with pytest.raises(ExtractError):
        buscar_janela(requests.Session(), 433, date(2024, 1, 1), date(2024, 1, 31))


@responses.activate
def test_extrair_serie_incremental_pede_so_o_periodo_novo() -> None:
    responses.get(URL_433, json=[{"data": "01/06/2024", "valor": "0.21"}])

    registros = extrair_serie(
        requests.Session(), IPCA, ultima_data=date(2024, 5, 1), hoje=date(2024, 6, 15)
    )

    assert registros == [{"data": "01/06/2024", "valor": "0.21"}]
    params = responses.calls[0].request.params
    assert params["dataInicial"] == "02/05/2024"
    assert params["dataFinal"] == "15/06/2024"


@responses.activate
def test_extrair_serie_em_dia_nao_chama_a_api() -> None:
    registros = extrair_serie(
        requests.Session(), IPCA, ultima_data=date(2024, 6, 15), hoje=date(2024, 6, 15)
    )

    assert registros == []
    assert len(responses.calls) == 0


@responses.activate
def test_extrair_serie_carga_historica_usa_varias_janelas() -> None:
    responses.get(URL_433, json=[{"data": "01/01/2005", "valor": "0.58"}])
    responses.get(URL_433, json=[{"data": "01/01/2015", "valor": "1.24"}])
    responses.get(URL_433, json=[{"data": "01/01/2024", "valor": "0.42"}])

    registros = extrair_serie(requests.Session(), IPCA, ultima_data=None, hoje=date(2024, 6, 15))

    assert [r["data"] for r in registros] == ["01/01/2005", "01/01/2015", "01/01/2024"]
    assert len(responses.calls) == 3
    assert responses.calls[0].request.params["dataInicial"] == "01/01/2000"
    assert responses.calls[2].request.params["dataFinal"] == "15/06/2024"


@responses.activate
def test_extrair_serie_descarta_pontos_fora_do_periodo_pedido() -> None:
    responses.get(
        URL_433,
        json=[{"data": "01/05/2024", "valor": "0.46"}, {"data": "01/06/2024", "valor": "0.21"}],
    )

    registros = extrair_serie(
        requests.Session(), IPCA, ultima_data=date(2024, 5, 1), hoje=date(2024, 6, 15)
    )

    assert registros == [{"data": "01/06/2024", "valor": "0.21"}]
