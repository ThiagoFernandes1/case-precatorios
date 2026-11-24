from datetime import date
from decimal import Decimal

from limpeza.leitura import Registro
from limpeza.modelo import CORRIGIDO, DESCARTADO, EM_DUVIDA, Precatorio
from limpeza.pagamentos import processar

PROC = "0012345-10.2019.8.26.0053"
DIGITOS = "00123451020198260053"


def evento(evento_id, valor, *, processo=PROC, tipo="pagamento", data="2025-05-10",
           atualizado="2025-05-10T10:00:00-03:00", linha=1):
    return Registro(linha, {"evento_id": evento_id, "processo": processo, "valor": valor,
                            "data_pagamento": data, "tipo": tipo, "atualizado_em": atualizado})


def carteira(apresentado=date(2025, 1, 10)):
    return {DIGITOS: Precatorio(processo=DIGITOS, apresentado_em=apresentado)}


def total(registros, precatorios=None):
    precatorios = precatorios or carteira()
    processar(registros, precatorios)
    return precatorios[DIGITOS].total_pago


def test_reprocessar_o_mesmo_arquivo_nao_muda_o_total():
    # É o cenário do operador que roda o script de novo, e também o das janelas de
    # 7 dias: o mesmo evento chega em vários arquivos.
    arquivo = [evento("ev-1", 1000, linha=1), evento("ev-2", 500, linha=2)]

    assert total(arquivo) == total(arquivo + arquivo) == total(arquivo * 7) == Decimal("1500.00")


def test_copia_identica_e_descartada_com_referencia_a_original():
    _, ocorrencias = processar([evento("ev-1", 1000, linha=1), evento("ev-1", 1000, linha=9)], carteira())

    descartes = [o for o in ocorrencias if o.situacao == DESCARTADO]
    assert [o.linha for o in descartes] == [9]
    assert "linha 1" in descartes[0].motivo


def test_vale_a_versao_mais_recente_mesmo_aparecendo_antes_no_arquivo():
    recente = evento("ev-1", Decimal("15500.0"), atualizado="2025-05-11T09:00:00-03:00", linha=1)
    antiga = evento("ev-1", Decimal("15000.0"), atualizado="2025-05-10T10:00:00-03:00", linha=9)

    assert total([recente, antiga]) == Decimal("15500.00")


def test_versoes_diferentes_com_o_mesmo_atualizado_em_ficam_em_duvida():
    a = evento("ev-1", 100, linha=1)
    b = evento("ev-1", 200, linha=2)
    precatorios = carteira()

    pagamentos, ocorrencias = processar([a, b], precatorios)

    assert pagamentos == []
    assert {o.situacao for o in ocorrencias} == {EM_DUVIDA}


def test_estorno_subtrai_em_vez_de_somar():
    registros = [evento("ev-1", 5000, data="2025-02-20", atualizado="2025-02-20T10:00:00-03:00"),
                 evento("ev-2", 5000, tipo="estorno", data="2025-02-21", atualizado="2025-02-21T10:00:00-03:00")]

    assert total(registros) == Decimal("0.00")


def test_estorno_sem_pagamento_antes_fica_em_duvida():
    precatorios = carteira()
    pagamentos, _ = processar([evento("ev-1", 300, tipo="estorno")], precatorios)

    assert pagamentos[0].situacao == EM_DUVIDA
    assert precatorios[DIGITOS].total_pago == 0


def test_evento_sem_valor_nao_entra_no_total_nem_some_do_relatorio():
    precatorios = carteira()
    _, ocorrencias = processar([evento("ev-1", None, linha=34)], precatorios)

    assert precatorios[DIGITOS].total_pago == 0
    assert ocorrencias[0].linha == 34 and ocorrencias[0].situacao == EM_DUVIDA


def test_valor_negativo_em_pagamento_fica_em_duvida():
    _, ocorrencias = processar([evento("ev-1", -200)], carteira())

    assert ocorrencias[0].situacao == EM_DUVIDA


def test_processo_vazio_ou_desconhecido_fica_em_duvida():
    _, ocorrencias = processar([evento("ev-1", 750, processo=""),
                                evento("ev-2", 750, processo="0099999-11.2020.8.26.0053")], carteira())

    assert [o.situacao for o in ocorrencias] == [EM_DUVIDA, EM_DUVIDA]


def test_valor_e_data_no_formato_brasileiro_sao_corrigidos():
    pagamentos, _ = processar([evento("ev-1", "2.500,50", data="10/04/2025",
                                      atualizado="2025-04-10T09:00:00-03:00")], carteira())

    p = pagamentos[0]
    assert p.situacao == CORRIGIDO
    assert p.valor == Decimal("2500.50")
    assert p.data_pagamento == date(2025, 4, 10)


def test_data_dd_mm_com_as_duas_leituras_possiveis_fica_em_duvida():
    # 03/04/2025 pode ser 3 de abril ou 4 de março; as duas são antes da atualização.
    pagamentos, _ = processar([evento("ev-1", 100, data="03/04/2025",
                                      atualizado="2025-05-10T10:00:00-03:00")], carteira())

    assert pagamentos[0].situacao == EM_DUVIDA


def test_pagamento_antes_da_apresentacao_fica_em_duvida_e_fora_do_total():
    precatorios = carteira(apresentado=date(2025, 4, 2))
    processar([evento("ev-1", 15500, data="2025-03-10", atualizado="2025-03-11T09:00:00-03:00")], precatorios)

    assert precatorios[DIGITOS].total_pago == 0
    assert precatorios[DIGITOS].valor_em_duvida == Decimal("15500.00")


def test_processo_sem_mascara_e_atribuido_ao_mesmo_precatorio():
    assert total([evento("ev-1", 1200, processo=DIGITOS)]) == Decimal("1200.00")
