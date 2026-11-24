"""Roda a limpeza nos arquivos reais do case e confere os pontos que mais pesam no negócio."""
import csv
import hashlib
from decimal import Decimal
from pathlib import Path

import pytest

from limpeza.__main__ import main

ENTRADA = Path(__file__).resolve().parents[1] / "recebido" / "dados"


def _hashes():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(ENTRADA.iterdir())}


@pytest.fixture(scope="module")
def saida(tmp_path_factory):
    destino = tmp_path_factory.mktemp("saida")
    antes = _hashes()
    main(["--entrada", str(ENTRADA), "--saida", str(destino), "--data-referencia", "2026-11-24"])
    assert _hashes() == antes, "a limpeza alterou um arquivo de origem"
    return destino


def _ler(caminho):
    with caminho.open(encoding="utf-8", newline="") as f:
        return {linha[next(iter(linha))]: linha for linha in csv.DictReader(f)}


def test_prazos_errados_do_hub_sao_corrigidos(saida):
    ps = _ler(saida / "precatorios.csv")
    assert ps["0012345-10.2019.8.26.0053"]["prazo_pagamento"] == "2026-12-31"  # hub: 2027
    assert ps["0056789-54.2017.4.03.6100"]["prazo_pagamento"] == "2026-12-31"  # hub: 2027
    assert ps["0045678-43.2021.5.02.0011"]["prazo_pagamento"] == "2026-12-31"


def test_totais_pagos(saida):
    ps = _ler(saida / "precatorios.csv")
    pago = {k: Decimal(v["total_pago"]) for k, v in ps.items()}
    assert pago["0012345-10.2019.8.26.0053"] == Decimal("2500.50")  # ev-001 em dúvida, ev-002 uma vez só
    assert pago["0023456-21.2020.8.26.0053"] == Decimal("9200.00")  # ev-003 + ev-005 sem máscara
    assert pago["0034567-32.2018.8.26.0405"] == Decimal("0.00")  # pagamento estornado
    assert pago["0067890-65.2016.8.26.0053"] == Decimal("4000.00")  # precatório que falta no hub
    assert sum(pago.values()) == Decimal("18700.50")


def test_todo_registro_de_pagamento_aparece_no_relatorio(saida):
    with (saida / "decisoes.csv").open(encoding="utf-8", newline="") as f:
        linhas = {int(d["linha"]) for d in csv.DictReader(f) if d["arquivo"] == "pagamentos.json" and d["linha"]}
    assert linhas == {2, 10, 18, 26, 34, 42, 50, 58, 66, 74, 82, 90, 98}


def test_saida_dentro_da_entrada_e_recusada():
    with pytest.raises(SystemExit):
        main(["--entrada", str(ENTRADA), "--saida", str(ENTRADA / "x")])
