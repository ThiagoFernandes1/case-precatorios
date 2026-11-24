from datetime import date
from decimal import Decimal

from limpeza.leitura import Registro
from limpeza.modelo import CORRIGIDO, EM_DUVIDA, OK
from limpeza.precatorios import consolidar

A = "0012345-10.2019.8.26.0053"
B = "0023456-21.2020.8.26.0053"


def trib(processo, ente="Município de São Paulo", valor="45.000,00", linha=2):
    return Registro(linha, {"numero_processo": processo, "ente_devedor": ente, "valor_face": valor})


def hub(processo, ente="MUNICIPIO DE SAO PAULO", valor="45000.00", apresentado="2025-01-10", prazo="2026-12-31", linha=2):
    return Registro(linha, {"processo": processo, "ente": ente, "valor_face": valor,
                            "apresentado_em": apresentado, "prazo_pagamento": prazo})


def apres(processo, quando, linha=2):
    return Registro(linha, {"processo": processo, "apresentado_em": quando})


def test_mesmo_precatorio_escrito_de_outro_jeito_nao_e_divergencia():
    ps, _ = consolidar([trib(A)], [hub("00123451020198260053")], [apres(A, "2025-01-10")])

    p = ps["00123451020198260053"]
    assert p.situacao == OK
    assert p.valor_face == Decimal("45000.00")
    assert len(p.diferencas_de_forma) == 2  # máscara e acento: a comparação exata acusaria


def test_ente_diferente_de_verdade_fica_em_duvida_e_mantem_o_do_tribunal():
    ps, _ = consolidar([trib(A, ente="União")], [hub(A, ente="Município de Santos")], [apres(A, "2025-01-10")])

    p = ps["00123451020198260053"]
    assert p.situacao == EM_DUVIDA
    assert p.ente_devedor == "União"
    assert p.ente_hub == "Município de Santos"


def test_valor_de_face_divergente_fica_em_duvida():
    ps, _ = consolidar([trib(A, valor="30.000,00")], [hub(A, valor="31000.00")], [apres(A, "2025-01-10")])

    assert ps["00123451020198260053"].situacao == EM_DUVIDA


def test_precatorio_que_so_existe_em_uma_das_listas_aparece_na_base_em_duvida():
    ps, _ = consolidar([trib(A)], [hub(B)], [])

    assert ps["00123451020198260053"].situacao == EM_DUVIDA
    assert ps["00234562120208260053"].situacao == EM_DUVIDA
    assert ps["00234562120208260053"].ente_devedor == "MUNICIPIO DE SAO PAULO"  # sem o tribunal, fica o do hub


def test_prazo_do_hub_errado_e_recalculado_pelo_dia_em_brasilia():
    ps, _ = consolidar([trib(A)], [hub(A, apresentado="2025-04-03T01:00:00Z", prazo="2027-12-31")],
                       [apres(A, "2025-04-03T01:00:00Z")])

    p = ps["00123451020198260053"]
    assert p.apresentado_em == date(2025, 4, 2)
    assert p.prazo_pagamento == date(2026, 12, 31)
    assert p.situacao == CORRIGIDO


def test_processo_invalido_na_origem_nao_entra_e_vira_ocorrencia():
    ps, ocorrencias = consolidar([trib("123")], [], [])

    assert ps == {}
    assert any(o.situacao == EM_DUVIDA and o.linha == 2 for o in ocorrencias)
