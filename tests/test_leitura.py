from decimal import Decimal

from limpeza.leitura import ler_csv, ler_json_lista


def test_csv_do_excel_em_cp1252_com_ponto_e_virgula(tmp_path):
    arquivo = tmp_path / "tribunal.csv"
    arquivo.write_bytes("numero_processo;ente_devedor;valor_face\r\n1;Município de São Paulo;45.000,00\r\n".encode("cp1252"))

    registros, info = ler_csv(arquivo, ["numero_processo", "ente_devedor", "valor_face"])

    assert info.encoding == "cp1252"
    assert info.delimitador == ";"
    assert info.fim_de_linha == "CRLF"
    assert registros[0].linha == 2
    assert registros[0].dados["ente_devedor"] == "Município de São Paulo"
    assert registros[0].dados["valor_face"] == "45.000,00"


def test_csv_utf8_com_bom_nao_suja_o_nome_da_primeira_coluna(tmp_path):
    arquivo = tmp_path / "hub.csv"
    arquivo.write_bytes("﻿processo,ente\n1,São Paulo\n".encode("utf-8"))

    registros, info = ler_csv(arquivo, ["processo", "ente"])

    assert info.encoding == "utf-8"
    assert registros[0].dados == {"processo": "1", "ente": "São Paulo"}


def test_json_guarda_linha_de_cada_objeto_e_le_decimal_sem_float(tmp_path):
    arquivo = tmp_path / "p.json"
    arquivo.write_text('[\n  {"a": 0.1},\n  {"a": 15000.0}\n]', encoding="utf-8")

    registros, _ = ler_json_lista(arquivo)

    assert [r.linha for r in registros] == [2, 3]
    assert registros[0].dados["a"] == Decimal("0.1")
    assert isinstance(registros[1].dados["a"], Decimal)
