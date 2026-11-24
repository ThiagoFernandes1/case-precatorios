"""Uso: python -m limpeza [--entrada recebido/dados] [--saida saida] [--data-referencia AAAA-MM-DD]"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from .pipeline import executar
from .relatorio import escrever


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m limpeza", description=__doc__)
    parser.add_argument("--entrada", type=Path, default=Path("recebido/dados"))
    parser.add_argument("--saida", type=Path, default=Path("saida"))
    parser.add_argument("--data-referencia", type=date.fromisoformat, default=date.today(),
                        help="data usada para marcar prazo vencido (padrão: hoje)")
    args = parser.parse_args(argv)

    entrada, saida = args.entrada.resolve(), args.saida.resolve()
    if saida == entrada or entrada in saida.parents:
        parser.error("a saída não pode ficar dentro da pasta de entrada: os originais não podem ser tocados")

    resultado = executar(entrada, args.data_referencia)
    escrever(resultado, saida)

    duvidas = sum(o.situacao == "em_duvida" for o in resultado.ocorrencias)
    print(f"Base gerada em {saida}. {len(resultado.precatorios)} precatórios, "
          f"{len(resultado.pagamentos)} eventos de pagamento, {duvidas} registros em dúvida.")
    print(f"Veja {saida / 'relatorio.md'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
