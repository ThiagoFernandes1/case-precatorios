"""Junta tribunal.csv, hub.csv e apresentacoes.json em um cadastro único por processo.

Decisão: para ente e valor de face, o tribunal é a referência (é quem emite o precatório).
O valor do hub fica ao lado para a operação ver a divergência, nunca é descartado em silêncio.
"""
from __future__ import annotations

from datetime import date

from .leitura import Registro
from .modelo import AVISO, CORRIGIDO, EM_DUVIDA, Ocorrencia, Precatorio
from .normalizacao import (
    ValorInvalido,
    chave_ente,
    dia_da_apresentacao,
    dv_cnj_valido,
    formatar_cnj,
    normalizar_cnj,
    parse_valor,
    prazo_pagamento,
)


def _indexar(registros: list[Registro], arquivo: str, campo: str, ocorrencias: list[Ocorrencia]) -> dict[str, Registro]:
    """Indexa por processo normalizado. Registro com processo inválido ou repetido vira dúvida."""
    indice: dict[str, Registro] = {}
    for reg in registros:
        bruto = reg.dados.get(campo)
        try:
            processo = normalizar_cnj(bruto)
        except ValorInvalido as erro:
            ocorrencias.append(Ocorrencia(arquivo, reg.linha, str(bruto), EM_DUVIDA, f"{erro}; registro fora da base"))
            continue
        if processo in indice:
            anterior = indice[processo].linha
            ocorrencias.append(
                Ocorrencia(arquivo, reg.linha, formatar_cnj(processo), EM_DUVIDA,
                           f"processo repetido no mesmo arquivo (primeira vez na linha {anterior}); mantida a primeira")
            )
            continue
        if str(bruto).strip() != formatar_cnj(processo):
            ocorrencias.append(
                Ocorrencia(arquivo, reg.linha, formatar_cnj(processo), CORRIGIDO,
                           f"processo gravado sem máscara ({str(bruto).strip()}); normalizado para casar com as outras fontes")
            )
        indice[processo] = reg
    return indice


def _valor(reg: Registro, campo: str, arquivo: str, chave: str, ocorrencias: list[Ocorrencia]):
    try:
        return parse_valor(reg.dados.get(campo))
    except ValorInvalido as erro:
        ocorrencias.append(Ocorrencia(arquivo, reg.linha, chave, EM_DUVIDA, f"valor de face: {erro}"))
        return None


def consolidar(
    tribunal: list[Registro],
    hub: list[Registro],
    apresentacoes: list[Registro],
) -> tuple[dict[str, Precatorio], list[Ocorrencia]]:
    ocorrencias: list[Ocorrencia] = []
    idx_trib = _indexar(tribunal, "tribunal.csv", "numero_processo", ocorrencias)
    idx_hub = _indexar(hub, "hub.csv", "processo", ocorrencias)
    idx_apres = _indexar(apresentacoes, "apresentacoes.json", "processo", ocorrencias)

    precatorios: dict[str, Precatorio] = {}
    for processo in sorted(idx_trib.keys() | idx_hub.keys() | idx_apres.keys()):
        cnj = formatar_cnj(processo)
        p = Precatorio(processo=processo)
        t, h, a = idx_trib.get(processo), idx_hub.get(processo), idx_apres.get(processo)

        if t:
            p.no_tribunal = True
            p.ente_devedor = (t.dados.get("ente_devedor") or "").strip() or None
            p.valor_face = _valor(t, "valor_face", "tribunal.csv", cnj, ocorrencias)
        if h:
            p.no_hub = True
            p.ente_hub = (h.dados.get("ente") or "").strip() or None
            p.valor_face_hub = _valor(h, "valor_face", "hub.csv", cnj, ocorrencias)
            p.prazo_hub = (h.dados.get("prazo_pagamento") or "").strip() or None

        if t and not h:
            p.marcar(EM_DUVIDA, "está na lista do tribunal mas não no hub: a operação não enxerga este precatório")
        if h and not t:
            p.marcar(EM_DUVIDA, "está no hub mas não na lista do tribunal: pode ter sido pago, cancelado ou ser de outra lista")
            p.ente_devedor, p.valor_face = p.ente_hub, p.valor_face_hub

        if t and h:
            _comparar(p, t, h)
            if str(t.dados.get("numero_processo", "")).strip() != str(h.dados.get("processo", "")).strip():
                p.diferencas_de_forma.append("número do processo escrito de outro jeito")
            if p.ente_devedor != p.ente_hub and chave_ente(p.ente_devedor) == chave_ente(p.ente_hub):
                p.diferencas_de_forma.append("nome do ente difere só em acento ou caixa")

        _apresentacao(p, a, h)

        if p.ente_devedor is None:
            p.marcar(EM_DUVIDA, "sem nome do ente devedor")
        if p.valor_face is None:
            p.marcar(EM_DUVIDA, "sem valor de face válido")
        precatorios[processo] = p

    # Registro de precatório inválido ou duplicado na origem também marca o precatório.
    for oc in ocorrencias:
        try:
            p = precatorios.get(normalizar_cnj(oc.chave))
        except ValorInvalido:
            continue
        if p is not None and oc.situacao == EM_DUVIDA:
            p.marcar(EM_DUVIDA, f"{oc.arquivo} linha {oc.linha}: {oc.motivo}")

    invalidos = [formatar_cnj(k) for k in precatorios if not dv_cnj_valido(k)]
    if invalidos:
        ocorrencias.append(
            Ocorrencia("todos", None, "dígito verificador", AVISO,
                       f"{len(invalidos)} de {len(precatorios)} processos têm DV CNJ inválido. Esperado se os números "
                       "são fictícios; em produção isso deveria barrar o registro.")
        )
    return precatorios, ocorrencias


def _comparar(p: Precatorio, t: Registro, h: Registro) -> None:
    if p.ente_devedor and p.ente_hub and chave_ente(p.ente_devedor) != chave_ente(p.ente_hub):
        p.marcar(EM_DUVIDA, f"ente diverge: tribunal '{p.ente_devedor}' (tribunal.csv linha {t.linha}), "
                            f"hub '{p.ente_hub}' (hub.csv linha {h.linha})")
    if p.valor_face is not None and p.valor_face_hub is not None and p.valor_face != p.valor_face_hub:
        p.marcar(EM_DUVIDA, f"valor de face diverge: tribunal {p.valor_face} (tribunal.csv linha {t.linha}), "
                            f"hub {p.valor_face_hub} (hub.csv linha {h.linha}); mantido o do tribunal")


def _dia(bruto: str | None) -> date | None:
    try:
        return dia_da_apresentacao(bruto)
    except ValorInvalido:
        return None


def _apresentacao(p: Precatorio, a: Registro | None, h: Registro | None) -> None:
    bruto_a = (a.dados.get("apresentado_em") if a else None) or None
    bruto_h = ((h.dados.get("apresentado_em") or "").strip() if h else None) or None
    dia_a, dia_h = _dia(bruto_a), _dia(bruto_h)

    if bruto_a and dia_a is None:
        p.marcar(EM_DUVIDA, f"apresentacoes.json linha {a.linha}: data de apresentação ilegível ({bruto_a!r})")
    if dia_a and dia_h and dia_a != dia_h:
        p.marcar(EM_DUVIDA, f"data de apresentação diverge: apresentacoes.json {dia_a}, hub {dia_h}; usada a de apresentacoes.json")

    p.apresentado_em = dia_a or dia_h
    bruto = bruto_a if dia_a else bruto_h
    if p.apresentado_em is None:
        p.marcar(EM_DUVIDA, "sem data de apresentação: prazo não calculado")
        return

    if bruto[:10] != p.apresentado_em.isoformat():
        p.marcar(CORRIGIDO, f"apresentação veio como instante ({bruto}); no horário de Brasília o dia é {p.apresentado_em}")

    p.prazo_pagamento = prazo_pagamento(p.apresentado_em)
    if p.prazo_hub and p.prazo_hub != p.prazo_pagamento.isoformat():
        motivo = ""
        if bruto[:10] != p.apresentado_em.isoformat():
            motivo = "; o hub parece ter usado a data escrita no campo, que está em UTC, e não o dia em Brasília"
        elif p.apresentado_em.month == 4 and p.apresentado_em.day == 2:
            motivo = "; apresentado exatamente em 2 de abril, que está dentro do \"até 2 de abril\""
        p.marcar(CORRIGIDO, f"prazo recalculado: hub dizia {p.prazo_hub}, o correto é {p.prazo_pagamento}{motivo}")
