from datetime import date
from decimal import Decimal

import pytest

from limpeza.normalizacao import (
    ValorInvalido,
    chave_ente,
    dia_da_apresentacao,
    dv_cnj_valido,
    formatar_cnj,
    normalizar_cnj,
    parse_data,
    parse_valor,
    prazo_pagamento,
)


# --- processo -------------------------------------------------------------------------------

def test_cnj_com_e_sem_mascara_viram_a_mesma_chave():
    assert normalizar_cnj("0023456-21.2020.8.26.0053") == normalizar_cnj("00234562120208260053")


@pytest.mark.parametrize("bruto", ["", "   ", None, "0023456-21.2020.8.26", "234562120208260053", "0023456-21-2020-8-26-0053"])
def test_cnj_incompleto_ou_mal_formado_e_rejeitado_e_nao_adivinhado(bruto):
    with pytest.raises(ValorInvalido):
        normalizar_cnj(bruto)


def test_formatar_cnj_devolve_a_mascara_original():
    assert formatar_cnj("00234562120208260053") == "0023456-21.2020.8.26.0053"


def test_digito_verificador_cnj():
    # 72 é o DV correto para 0012345-??.2019.8.26.0053 (calculado à mão pelo módulo 97)
    assert dv_cnj_valido(normalizar_cnj("0012345-72.2019.8.26.0053"))
    assert not dv_cnj_valido(normalizar_cnj("0012345-10.2019.8.26.0053"))


# --- valor ----------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bruto, esperado",
    [
        ("2.500,50", Decimal("2500.50")),
        ("45.000,00", Decimal("45000.00")),
        ("2500,5", Decimal("2500.50")),
        ("45000.00", Decimal("45000.00")),
        (Decimal("15000.0"), Decimal("15000.00")),
        (8000, Decimal("8000.00")),
        (-200, Decimal("-200.00")),
    ],
)
def test_valor_aceita_formatos_sem_ambiguidade(bruto, esperado):
    assert parse_valor(bruto) == esperado


@pytest.mark.parametrize("bruto", [None, True, "2.500", "1.234.567", "abc", "1,234.56", Decimal("10.005"), "NaN"])
def test_valor_ambiguo_ou_invalido_e_rejeitado(bruto):
    with pytest.raises(ValorInvalido):
        parse_valor(bruto)


# --- datas ----------------------------------------------------------------------------------

def test_data_brasileira_e_lida_como_dia_mes_e_devolve_a_outra_leitura():
    data, alternativa = parse_data("10/04/2025")
    assert data == date(2025, 4, 10)
    assert alternativa == "2025-10-04"


def test_data_brasileira_sem_ambiguidade_nao_tem_alternativa():
    assert parse_data("25/04/2025") == (date(2025, 4, 25), None)


def test_data_inexistente_e_rejeitada():
    with pytest.raises(ValorInvalido):
        parse_data("2025-02-30")


def test_29_de_fevereiro_em_ano_bissexto_e_valido():
    assert parse_data("2024-02-29") == (date(2024, 2, 29), None)


@pytest.mark.parametrize(
    "bruto, dia",
    [
        ("2025-04-02", date(2025, 4, 2)),
        ("2025-04-02T23:30:00-03:00", date(2025, 4, 2)),  # em UTC já seria dia 3
        ("2025-04-03T01:00:00Z", date(2025, 4, 2)),  # 22h do dia 2 em Brasília
        ("2025-04-03T03:00:00Z", date(2025, 4, 3)),  # meia-noite do dia 3 em Brasília
        # Em 1/1/2019 São Paulo estava em horário de verão (UTC-2). Com UTC-3 fixo esta
        # apresentação cairia em 2018 e o prazo sairia um ano antes.
        ("2019-01-01T02:30:00Z", date(2019, 1, 1)),
    ],
)
def test_dia_da_apresentacao_usa_o_calendario_de_brasilia(bruto, dia):
    assert dia_da_apresentacao(bruto) == dia


# --- prazo ----------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "apresentacao, prazo",
    [
        (date(2025, 4, 2), date(2026, 12, 31)),  # no limite: "até 2 de abril" inclui o dia 2
        (date(2025, 4, 3), date(2027, 12, 31)),
        (date(2025, 1, 1), date(2026, 12, 31)),
        (date(2025, 12, 31), date(2027, 12, 31)),
        (date(2024, 2, 29), date(2025, 12, 31)),
        (date(2023, 12, 31), date(2025, 12, 31)),
    ],
)
def test_prazo_constitucional(apresentacao, prazo):
    assert prazo_pagamento(apresentacao) == prazo


# --- ente -----------------------------------------------------------------------------------

def test_chave_do_ente_ignora_acento_caixa_e_espacos():
    assert chave_ente("MUNICIPIO DE SAO PAULO") == chave_ente(" Município  de São Paulo ")
    assert chave_ente("União") != chave_ente("Município de Santos")
