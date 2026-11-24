"""Tratamento dos eventos de pagamento.

Ordem das regras:
1. Agrupa por evento_id. Cópias idênticas são descartadas; se o mesmo evento vem com
   conteúdos diferentes, vale a versão com maior atualizado_em (as outras são descartadas).
2. Valida a versão escolhida. Formato corrigível vira correção; o que não dá para ler ou
   atribuir a um precatório fica em dúvida e não entra no total.
3. Checa coerência com o precatório (pagamento antes da apresentação, estorno sem
   pagamento para estornar).

Como o resultado depende só do conjunto de eventos, e não de quantas vezes cada um aparece,
processar o mesmo arquivo duas vezes (ou dois arquivos de janelas que se sobrepõem) dá o
mesmo total. É exatamente o que o script atual não garante.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from .leitura import Registro
from .modelo import CORRIGIDO, DESCARTADO, EM_DUVIDA, Ocorrencia, Pagamento, Precatorio
from .normalizacao import (
    FUSO_TRIBUNAL,
    ValorInvalido,
    formatar_cnj,
    normalizar_cnj,
    parse_data,
    parse_instante,
    parse_valor,
)

ARQUIVO = "pagamentos.json"
TIPOS = {"pagamento", "estorno"}


class _Duvida(Exception):
    """O evento não pode entrar na base nem com correção."""


def processar(
    registros: list[Registro], precatorios: dict[str, Precatorio]
) -> tuple[list[Pagamento], list[Ocorrencia]]:
    ocorrencias: list[Ocorrencia] = []
    grupos: dict[str, list[Registro]] = defaultdict(list)

    for reg in registros:
        evento_id = str(reg.dados.get("evento_id") or "").strip()
        if not evento_id:
            ocorrencias.append(Ocorrencia(ARQUIVO, reg.linha, "(sem evento_id)", EM_DUVIDA,
                                          "evento sem identificador: não dá para saber se é repetição de outro"))
            continue
        grupos[evento_id].append(reg)

    pagamentos: list[Pagamento] = []
    for evento_id, versoes in grupos.items():
        escolhido = _escolher_versao(evento_id, versoes, ocorrencias)
        if escolhido is None:
            continue
        try:
            pagamento = _validar(evento_id, escolhido, precatorios)
        except _Duvida as duvida:
            ocorrencias.append(Ocorrencia(ARQUIVO, escolhido.linha, evento_id, EM_DUVIDA, str(duvida)))
            _avisar_precatorio(escolhido, precatorios, f"evento {evento_id} em dúvida: {duvida}")
            continue
        pagamentos.append(pagamento)

    _checar_estornos(pagamentos)
    _somar(pagamentos, precatorios)

    for p in pagamentos:
        motivo = "; ".join(p.observacoes) or "importado sem alteração"
        ocorrencias.append(Ocorrencia(ARQUIVO, p.linha, p.evento_id, p.situacao, motivo))
    ocorrencias.sort(key=lambda o: (o.linha or 0))
    return pagamentos, ocorrencias


def _escolher_versao(evento_id: str, versoes: list[Registro], ocorrencias: list[Ocorrencia]) -> Registro | None:
    distintas: list[Registro] = []
    for reg in versoes:
        igual = next((d for d in distintas if d.dados == reg.dados), None)
        if igual:
            ocorrencias.append(Ocorrencia(ARQUIVO, reg.linha, evento_id, DESCARTADO,
                                          f"cópia idêntica do registro da linha {igual.linha}"))
        else:
            distintas.append(reg)

    if len(distintas) == 1:
        return distintas[0]

    try:
        datadas = sorted(((parse_instante(r.dados.get("atualizado_em")), r) for r in distintas),
                         key=lambda par: par[0])
    except ValorInvalido as erro:
        for reg in distintas:
            ocorrencias.append(Ocorrencia(ARQUIVO, reg.linha, evento_id, EM_DUVIDA,
                                          f"evento com versões diferentes e atualizado_em ilegível ({erro})"))
        return None

    mais_recente, escolhido = datadas[-1]
    empatados = [r for quando, r in datadas if quando == mais_recente]
    if len(empatados) > 1:
        linhas = ", ".join(str(r.linha) for r in empatados)
        for reg in distintas:
            ocorrencias.append(Ocorrencia(ARQUIVO, reg.linha, evento_id, EM_DUVIDA,
                                          f"versões diferentes com o mesmo atualizado_em (linhas {linhas})"))
        return None

    for quando, reg in datadas[:-1]:
        ocorrencias.append(Ocorrencia(
            ARQUIVO, reg.linha, evento_id, DESCARTADO,
            f"versão antiga (atualizado_em {quando.isoformat()}, valor {reg.dados.get('valor')}); "
            f"substituída pela da linha {escolhido.linha} (atualizado_em {mais_recente.isoformat()}, "
            f"valor {escolhido.dados.get('valor')})",
        ))
    return escolhido


def _validar(evento_id: str, reg: Registro, precatorios: dict[str, Precatorio]) -> Pagamento:
    d = reg.dados
    correcoes: list[str] = []
    duvidas: list[str] = []
    observacoes: list[str] = []

    bruto_processo = d.get("processo")
    try:
        processo = normalizar_cnj(bruto_processo)
    except ValorInvalido as erro:
        raise _Duvida(f"{erro}; valor {d.get('valor')} sem precatório para atribuir") from None
    if processo not in precatorios:
        raise _Duvida(f"processo {formatar_cnj(processo)} não está no tribunal, no hub nem nas apresentações")
    if str(bruto_processo).strip() != formatar_cnj(processo):
        correcoes.append(f"processo sem máscara ({bruto_processo}) normalizado")

    tipo = str(d.get("tipo") or "").strip().lower()
    if tipo not in TIPOS:
        raise _Duvida(f"tipo desconhecido: {d.get('tipo')!r}")
    if tipo == "estorno":
        observacoes.append("tipo 'estorno' não está na documentação (que diz 'sempre pagamento'); "
                           "subtraído do total, como o banco já prevê")

    try:
        valor = parse_valor(d.get("valor"))
    except ValorInvalido as erro:
        raise _Duvida(str(erro)) from None
    if valor < 0:
        raise _Duvida(f"valor negativo ({valor}) em evento do tipo '{tipo}': pode ser um estorno lançado "
                      "com o tipo errado, mas não há como confirmar")
    if valor == 0:
        raise _Duvida("valor zero")
    if isinstance(d.get("valor"), str):
        correcoes.append(f"valor veio como texto no formato brasileiro ({d['valor']!r}); lido como {valor}")

    try:
        atualizado_em = parse_instante(d.get("atualizado_em"))
    except ValorInvalido as erro:
        raise _Duvida(f"atualizado_em: {erro}") from None
    dia_atualizacao = atualizado_em.astimezone(FUSO_TRIBUNAL).date()

    try:
        data_pagamento, alternativa = parse_data(d.get("data_pagamento"))
    except ValorInvalido as erro:
        raise _Duvida(f"data_pagamento: {erro}") from None
    if data_pagamento.isoformat() != str(d.get("data_pagamento")).strip():
        if alternativa and alternativa <= dia_atualizacao.isoformat():
            duvidas.append(f"data {d['data_pagamento']!r} pode ser {data_pagamento} ou {alternativa}")
        elif alternativa:
            correcoes.append(f"data {d['data_pagamento']!r} lida como {data_pagamento}; a leitura {alternativa} "
                             f"seria depois da última atualização do registro ({dia_atualizacao})")
        else:
            correcoes.append(f"data {d['data_pagamento']!r} convertida para {data_pagamento}")

    if data_pagamento > dia_atualizacao:
        duvidas.append(f"pagamento em {data_pagamento}, depois da última atualização do registro ({dia_atualizacao})")

    apresentacao = precatorios[processo].apresentado_em
    if apresentacao and data_pagamento < apresentacao:
        duvidas.append(f"pagamento em {data_pagamento}, antes da apresentação do precatório ({apresentacao})")

    pagamento = Pagamento(evento_id, processo, tipo, valor, data_pagamento, atualizado_em, ARQUIVO, reg.linha)
    pagamento.observacoes.extend(observacoes)
    for texto in correcoes:
        pagamento.marcar(CORRIGIDO, texto)
    for texto in duvidas:
        pagamento.marcar(EM_DUVIDA, texto)
    return pagamento


def _checar_estornos(pagamentos: list[Pagamento]) -> None:
    """Um estorno não pode deixar o total pago do processo negativo."""
    por_processo: dict[str, list[Pagamento]] = defaultdict(list)
    for p in pagamentos:
        if p.situacao != EM_DUVIDA:
            por_processo[p.processo].append(p)
    for eventos in por_processo.values():
        saldo = Decimal("0")
        # No mesmo dia, pagamento antes de estorno.
        for p in sorted(eventos, key=lambda e: (e.data_pagamento, e.tipo == "estorno")):
            if p.tipo == "estorno" and saldo - p.valor < 0:
                p.marcar(EM_DUVIDA, f"estorno de {p.valor} maior que o total pago até {p.data_pagamento} ({saldo})")
                continue
            saldo += p.valor_liquido


def _somar(pagamentos: list[Pagamento], precatorios: dict[str, Precatorio]) -> None:
    for p in pagamentos:
        precatorio = precatorios[p.processo]
        if p.situacao == EM_DUVIDA:
            precatorio.valor_em_duvida += p.valor_liquido
            precatorio.marcar(EM_DUVIDA, f"evento {p.evento_id} ({p.valor_liquido}) em dúvida, fora do total pago")
        else:
            precatorio.total_pago += p.valor_liquido


def _avisar_precatorio(reg: Registro, precatorios: dict[str, Precatorio], texto: str) -> None:
    try:
        precatorio = precatorios.get(normalizar_cnj(reg.dados.get("processo")))
    except ValorInvalido:
        return
    if precatorio is not None:
        precatorio.marcar(EM_DUVIDA, texto)
