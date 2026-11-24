"""Regras de normalização de campo.

Cada função devolve o valor normalizado ou levanta ValorInvalido com o motivo. Quem chama
decide se aquilo vira correção, descarte ou dúvida. A regra geral é: só corrijo quando
existe uma única leitura possível do dado; se houver duas, é dúvida.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

# Fuso usado para transformar um instante em "dia da apresentação". Suposição minha:
# o tribunal conta o dia no horário de Brasília (ver dúvidas no ANALISE.md).
FUSO_TRIBUNAL = ZoneInfo("America/Sao_Paulo")

CENTAVO = Decimal("0.01")


class ValorInvalido(ValueError):
    pass


# --- Número do processo (CNJ) -------------------------------------------------------------

_CNJ_COM_MASCARA = re.compile(r"(\d{7})-(\d{2})\.(\d{4})\.(\d)\.(\d{2})\.(\d{4})")
_CNJ_SO_DIGITOS = re.compile(r"\d{20}")


def normalizar_cnj(bruto) -> str:
    """Devolve os 20 dígitos do processo.

    Aceita só duas formas: máscara completa ou exatamente 20 dígitos. Qualquer outra coisa
    (máscara parcial, dígitos a menos) é rejeitada em vez de "consertada", porque completar
    zeros ou adivinhar a posição dos separadores pode juntar dois processos diferentes.
    """
    if bruto is None:
        raise ValorInvalido("processo ausente")
    texto = str(bruto).strip()
    if not texto:
        raise ValorInvalido("processo vazio")
    if _CNJ_SO_DIGITOS.fullmatch(texto):
        return texto
    encontrado = _CNJ_COM_MASCARA.fullmatch(texto)
    if encontrado:
        return "".join(encontrado.groups())
    raise ValorInvalido(f"processo fora do padrão CNJ: {texto!r}")


def formatar_cnj(digitos: str) -> str:
    d = digitos
    return f"{d[:7]}-{d[7:9]}.{d[9:13]}.{d[13]}.{d[14:16]}.{d[16:]}"


def dv_cnj_valido(digitos: str) -> bool:
    """Confere os dígitos verificadores (módulo 97, Resolução CNJ 65/2008)."""
    sequencial, dv, resto = digitos[:7], digitos[7:9], digitos[9:]
    return int(sequencial + resto + dv) % 97 == 1


# --- Valores em reais ---------------------------------------------------------------------

_VALOR_BR = re.compile(r"-?\d{1,3}(\.\d{3})*,\d{1,2}|-?\d+,\d{1,2}")  # 2.500,50 ou 2500,50
_VALOR_PONTO = re.compile(r"-?\d+(\.\d{1,2})?")  # 2500.50 ou 2500
_SO_MILHAR = re.compile(r"-?\d{1,3}(\.\d{3})+")  # 2.500: milhar BR ou 2,5 com três casas?


def parse_valor(bruto) -> Decimal:
    if bruto is None:
        raise ValorInvalido("valor ausente (null)")
    if isinstance(bruto, bool):
        raise ValorInvalido(f"valor booleano: {bruto!r}")
    if isinstance(bruto, (int, Decimal)):
        valor = Decimal(bruto)
    elif isinstance(bruto, float):
        # Não deveria acontecer (o JSON é lido com Decimal), mas se acontecer
        # str() devolve a menor representação que volta ao mesmo float.
        valor = Decimal(str(bruto))
    elif isinstance(bruto, str):
        valor = _parse_texto(bruto.strip())
    else:
        raise ValorInvalido(f"tipo de valor inesperado: {type(bruto).__name__}")

    if not valor.is_finite():
        raise ValorInvalido(f"valor não numérico: {bruto!r}")
    if valor != valor.quantize(CENTAVO):
        raise ValorInvalido(f"valor com mais de duas casas decimais: {bruto!r}")
    return valor.quantize(CENTAVO)


def _parse_texto(texto: str) -> Decimal:
    if _SO_MILHAR.fullmatch(texto):
        raise ValorInvalido(f"valor ambíguo (milhar brasileiro ou decimal com ponto?): {texto!r}")
    try:
        if _VALOR_BR.fullmatch(texto):
            return Decimal(texto.replace(".", "").replace(",", "."))
        if _VALOR_PONTO.fullmatch(texto):
            return Decimal(texto)
    except InvalidOperation:
        pass
    raise ValorInvalido(f"valor em formato não reconhecido: {texto!r}")


# --- Datas --------------------------------------------------------------------------------

_DATA_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")
_DATA_BR = re.compile(r"(\d{2})/(\d{2})/(\d{4})")


def parse_data(bruto) -> tuple[date, str | None]:
    """Devolve (data, formato_alternativo).

    formato_alternativo vem preenchido quando a data veio como DD/MM/AAAA: é a leitura
    MM/DD do mesmo texto, para quem chama decidir se a ambiguidade importa.
    """
    if bruto is None or not str(bruto).strip():
        raise ValorInvalido("data ausente")
    texto = str(bruto).strip()
    try:
        if _DATA_ISO.fullmatch(texto):
            return date.fromisoformat(texto), None
        encontrado = _DATA_BR.fullmatch(texto)
        if encontrado:
            dia, mes, ano = (int(p) for p in encontrado.groups())
            leitura = date(ano, mes, dia)
            alternativa = None
            if dia <= 12 and dia != mes:
                alternativa = date(ano, dia, mes).isoformat()
            return leitura, alternativa
    except ValueError as erro:
        raise ValorInvalido(f"data inexistente: {texto!r} ({erro})") from None
    raise ValorInvalido(f"data em formato não reconhecido: {texto!r}")


def parse_instante(bruto) -> datetime:
    """Data e hora com fuso. Sem fuso, assume o horário do tribunal."""
    if bruto is None or not str(bruto).strip():
        raise ValorInvalido("data e hora ausente")
    texto = str(bruto).strip()
    # fromisoformat só aceita "Z" a partir do Python 3.11; o projeto roda em 3.10.
    if texto.endswith(("Z", "z")):
        texto = texto[:-1] + "+00:00"
    try:
        instante = datetime.fromisoformat(texto)
    except ValueError:
        raise ValorInvalido(f"data e hora em formato não reconhecido: {bruto!r}") from None
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=FUSO_TRIBUNAL)
    return instante


def dia_da_apresentacao(bruto) -> date:
    """Dia da apresentação no calendário do tribunal.

    O campo vem às vezes como data pura e às vezes como data e hora com fuso. Quando tem
    hora, converto para o horário de Brasília antes de pegar o dia: 2025-04-03T01:00:00Z
    é 2 de abril às 22h em Brasília, e para o prazo isso é 2 de abril.
    """
    texto = "" if bruto is None else str(bruto).strip()
    if _DATA_ISO.fullmatch(texto):
        return date.fromisoformat(texto)
    return parse_instante(texto).astimezone(FUSO_TRIBUNAL).date()


# --- Prazo constitucional -----------------------------------------------------------------

def prazo_pagamento(apresentacao: date) -> date:
    """Apresentado até 2 de abril (inclusive): paga até 31/12 do ano seguinte.
    Depois de 2 de abril: até 31/12 do ano subsequente ao seguinte."""
    limite = date(apresentacao.year, 4, 2)
    anos = 1 if apresentacao <= limite else 2
    return date(apresentacao.year + anos, 12, 31)


# --- Nome do ente -------------------------------------------------------------------------

def chave_ente(nome: str | None) -> str:
    """Forma de comparação: sem acento, maiúscula, espaços simples.
    "MUNICIPIO DE SAO PAULO" e "Município de São Paulo" viram a mesma chave."""
    if not nome:
        return ""
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii")
    return " ".join(sem_acento.upper().split())
