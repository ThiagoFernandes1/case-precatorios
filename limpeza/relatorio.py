"""Escrita da base limpa (CSV) e do relatório (Markdown)."""
from __future__ import annotations

import csv
from collections import Counter
from decimal import Decimal
from pathlib import Path

from .modelo import CORRIGIDO, DESCARTADO, EM_DUVIDA, OK
from .normalizacao import formatar_cnj
from .pipeline import Resultado

SITUACOES = [OK, CORRIGIDO, DESCARTADO, EM_DUVIDA]


def _brl(valor: Decimal | None) -> str:
    if valor is None:
        return "-"
    texto = f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {texto}"


def _lista(processos) -> str:
    return ", ".join(formatar_cnj(p) for p in sorted(processos)) or "nenhum"


def _csv(caminho: Path, cabecalho: list[str], linhas: list[list]) -> None:
    with caminho.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.writer(f, lineterminator="\n")
        escritor.writerow(cabecalho)
        escritor.writerows(linhas)


def escrever(resultado: Resultado, saida: Path) -> None:
    saida.mkdir(parents=True, exist_ok=True)
    _precatorios_csv(resultado, saida / "precatorios.csv")
    _pagamentos_csv(resultado, saida / "pagamentos.csv")
    _decisoes_csv(resultado, saida / "decisoes.csv")
    (saida / "relatorio.md").write_text(_markdown(resultado), encoding="utf-8", newline="\n")


def _saldo(p) -> Decimal | None:
    return None if p.valor_face is None else p.valor_face - p.total_pago


def _vencido(p, resultado: Resultado) -> bool:
    return p.prazo_pagamento is not None and p.prazo_pagamento < resultado.data_referencia and (_saldo(p) or 0) > 0


def _precatorios_csv(r: Resultado, caminho: Path) -> None:
    linhas = []
    for p in r.precatorios.values():
        linhas.append([
            formatar_cnj(p.processo), p.ente_devedor or "", p.valor_face or "", p.apresentado_em or "",
            p.prazo_pagamento or "", "sim" if _vencido(p, r) else "nao", p.total_pago, p.valor_em_duvida,
            _saldo(p) if _saldo(p) is not None else "", "sim" if p.no_tribunal else "nao",
            "sim" if p.no_hub else "nao", p.ente_hub or "", p.valor_face_hub or "", p.prazo_hub or "",
            p.situacao, " | ".join(p.observacoes),
        ])
    _csv(caminho, ["numero_processo", "ente_devedor", "valor_face", "apresentado_em", "prazo_pagamento",
                   "vencido", "total_pago", "valor_em_duvida", "saldo", "no_tribunal", "no_hub", "ente_hub",
                   "valor_face_hub", "prazo_hub", "situacao", "observacoes"], linhas)


def _pagamentos_csv(r: Resultado, caminho: Path) -> None:
    linhas = []
    for p in sorted(r.pagamentos, key=lambda p: (p.processo, p.data_pagamento, p.evento_id)):
        linhas.append([
            p.evento_id, formatar_cnj(p.processo), p.tipo, p.valor, p.valor_liquido, p.data_pagamento,
            p.atualizado_em.isoformat(), p.linha, "nao" if p.situacao == EM_DUVIDA else "sim", p.situacao,
            " | ".join(p.observacoes),
        ])
    _csv(caminho, ["evento_id", "numero_processo", "tipo", "valor", "valor_liquido", "data_pagamento",
                   "atualizado_em", "linha_origem", "conta_no_total", "situacao", "observacoes"], linhas)


def _decisoes_csv(r: Resultado, caminho: Path) -> None:
    linhas = [[o.arquivo, o.linha or "", o.chave, o.situacao, o.motivo] for o in r.ocorrencias + r.avisos]
    _csv(caminho, ["arquivo", "linha", "chave", "situacao", "motivo"], linhas)


def _markdown(r: Resultado) -> str:
    ps = list(r.precatorios.values())
    oc_pag = [o for o in r.ocorrencias if o.arquivo == "pagamentos.json"]
    contagem = Counter(o.situacao for o in oc_pag)
    total_pago = sum((p.total_pago for p in ps), Decimal("0"))
    em_duvida = sum((p.valor_em_duvida for p in ps), Decimal("0"))
    em_ambos = [p for p in ps if p.no_tribunal and p.no_hub]
    ente_real = {p.processo for p in em_ambos if any(o.startswith("ente diverge") for o in p.observacoes)}
    valor_real = {p.processo for p in em_ambos if any(o.startswith("valor de face diverge") for o in p.observacoes)}
    so_forma = {p.processo for p in em_ambos if p.diferencas_de_forma} - ente_real

    s = []
    s.append("# Relatório da limpeza\n")
    s.append(f"Data de referência (para prazo vencido): {r.data_referencia.isoformat()}. "
             "Gerado por `python -m limpeza`. Os arquivos de origem não são alterados; "
             "o hash abaixo identifica exatamente qual versão foi lida.\n")

    s.append("## Arquivos lidos\n")
    s.append("| arquivo | sha256 (início) | codificação | separador | fim de linha |")
    s.append("|---|---|---|---|---|")
    for a in r.arquivos:
        s.append(f"| {a.caminho.name} | `{a.sha256[:16]}` | {a.encoding} | {a.delimitador or '-'} | {a.fim_de_linha} |")
    s.append("")

    s.append("## Resumo\n")
    s.append(f"- Registros em pagamentos.json: {len(oc_pag)}. "
             + ", ".join(f"{contagem.get(k, 0)} {k.replace('_', ' ')}" for k in SITUACOES) + ".")
    s.append(f"- Total pago confirmado: {_brl(total_pago)}. Em dúvida (fora do total): {_brl(em_duvida)}, "
             "mais os eventos em dúvida sem valor ou sem processo listados abaixo.")
    s.append(f"- Precatórios na base: {len(ps)} "
             f"({sum(p.no_tribunal and p.no_hub for p in ps)} nas duas listas, "
             f"{sum(p.no_tribunal and not p.no_hub for p in ps)} só no tribunal, "
             f"{sum(p.no_hub and not p.no_tribunal for p in ps)} só no hub).")
    s.append(f"- Comparação tribunal x hub: dos {len(em_ambos)} precatórios que estão nas duas listas, comparar "
             f"número e nome do ente exatamente como escritos marca {len(so_forma | ente_real)} como diferentes. "
             f"Em {len(so_forma)} a diferença é só de escrita (máscara, acento, caixa). Divergências reais: "
             f"ente em {_lista(ente_real)}; valor de face em {_lista(valor_real)}, que a comparação manual "
             "não olha.")
    prazos = [p for p in ps if p.prazo_hub and p.prazo_pagamento and p.prazo_hub != p.prazo_pagamento.isoformat()]
    s.append(f"- Prazos do hub recalculados: {len(prazos)} "
             f"({', '.join(formatar_cnj(p.processo) for p in prazos) or 'nenhum'}).")
    vencidos = [p for p in ps if _vencido(p, r)]
    s.append(f"- Vencidos com saldo em {r.data_referencia.isoformat()}: {len(vencidos)} "
             f"({', '.join(formatar_cnj(p.processo) for p in vencidos) or 'nenhum'}).\n")

    s.append("## Precatórios\n")
    s.append("| processo | ente | valor de face | apresentado | prazo | prazo no hub | pago | em dúvida | situação |")
    s.append("|---|---|---|---|---|---|---|---|---|")
    for p in ps:
        prazo = f"{p.prazo_pagamento}{' (vencido)' if _vencido(p, r) else ''}" if p.prazo_pagamento else "-"
        s.append(f"| {formatar_cnj(p.processo)} | {p.ente_devedor or '-'} | {_brl(p.valor_face)} | "
                 f"{p.apresentado_em or '-'} | {prazo} | {p.prazo_hub or '-'} | {_brl(p.total_pago)} | "
                 f"{_brl(p.valor_em_duvida)} | {p.situacao} |")
    s.append("")
    for p in ps:
        if p.observacoes:
            s.append(f"**{formatar_cnj(p.processo)}**\n")
            s += [f"- {o}" for o in p.observacoes]
            s.append("")

    s.append("## Pagamentos, registro a registro\n")
    s.append("| linha | evento | situação | motivo |")
    s.append("|---|---|---|---|")
    for o in oc_pag:
        s.append(f"| {o.linha or '-'} | {o.chave} | {o.situacao} | {o.motivo.replace('|', '/')} |")
    s.append("")

    outras = [o for o in r.ocorrencias if o.arquivo != "pagamentos.json"]
    if outras:
        s.append("## Ajustes nos cadastros\n")
        s += [f"- {o.arquivo}, linha {o.linha}: {o.chave}: {o.situacao}. {o.motivo}" for o in outras]
        s.append("")

    s.append("## Avisos sobre os arquivos\n")
    s += [f"- {o.arquivo}: {o.motivo}" for o in r.avisos]
    s.append("")
    return "\n".join(s)
