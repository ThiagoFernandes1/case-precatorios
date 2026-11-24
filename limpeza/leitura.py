"""Leitura dos arquivos como vieram, sem confiar no que a documentação diz sobre o formato.

Tudo que é descoberto na leitura (encoding, separador, fim de linha) volta junto com os
dados, para entrar no relatório. Nenhuma função daqui escreve em disco.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path


@dataclass
class Arquivo:
    caminho: Path
    sha256: str
    encoding: str
    fim_de_linha: str
    delimitador: str | None = None
    avisos: list[str] = field(default_factory=list)


@dataclass
class Registro:
    """Um registro do arquivo de origem, com a linha onde começa (para servir de evidência)."""

    linha: int
    dados: dict


def _decodificar(conteudo: bytes) -> tuple[str, str]:
    # UTF-8 é estrito: se um byte não for UTF-8 válido, falha. Por isso a ordem funciona:
    # um arquivo cp1252 com acento nunca passa como UTF-8 por engano.
    try:
        return conteudo.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        # cp1252 é o que o Excel em português grava quando salva "CSV".
        return conteudo.decode("cp1252"), "cp1252"


def _fim_de_linha(texto: str) -> str:
    if "\r\n" in texto:
        return "CRLF"
    if "\n" in texto:
        return "LF"
    return "nenhum"


def _abrir(caminho: Path) -> tuple[str, Arquivo]:
    conteudo = caminho.read_bytes()
    texto, encoding = _decodificar(conteudo)
    info = Arquivo(
        caminho=caminho,
        sha256=hashlib.sha256(conteudo).hexdigest(),
        encoding=encoding,
        fim_de_linha=_fim_de_linha(texto),
    )
    return texto, info


def _detectar_delimitador(cabecalho: str) -> str:
    candidatos = {d: cabecalho.count(d) for d in (",", ";", "\t")}
    delimitador = max(candidatos, key=candidatos.get)
    if candidatos[delimitador] == 0:
        raise ValueError(f"não consegui identificar o separador do cabeçalho: {cabecalho!r}")
    return delimitador


def ler_csv(caminho: Path, colunas_esperadas: list[str]) -> tuple[list[Registro], Arquivo]:
    texto, info = _abrir(caminho)
    primeira_linha = texto.splitlines()[0] if texto else ""
    info.delimitador = _detectar_delimitador(primeira_linha)

    leitor = csv.DictReader(io.StringIO(texto, newline=""), delimiter=info.delimitador)
    faltando = [c for c in colunas_esperadas if c not in (leitor.fieldnames or [])]
    if faltando:
        raise ValueError(f"{caminho.name}: colunas ausentes {faltando}; cabeçalho lido: {leitor.fieldnames}")

    registros = []
    for numero, linha in enumerate(leitor, start=2):  # linha 1 é o cabeçalho
        if None in linha:
            info.avisos.append(f"linha {numero}: mais colunas que o cabeçalho; excedente ignorado")
            linha.pop(None)
        registros.append(Registro(linha=numero, dados=linha))
    return registros, info


_SEPARADOR_JSON = re.compile(r"[\s,]*")


def ler_json_lista(caminho: Path) -> tuple[list[Registro], Arquivo]:
    """Lê uma lista JSON guardando a linha onde cada objeto começa.

    Números com casas decimais viram Decimal direto do texto, sem passar por float.
    """
    texto, info = _abrir(caminho)
    decodificador = json.JSONDecoder(parse_float=Decimal)

    dados = decodificador.decode(texto)  # valida o arquivo inteiro antes de percorrer
    if not isinstance(dados, list):
        raise ValueError(f"{caminho.name}: esperava uma lista JSON, veio {type(dados).__name__}")

    registros = []
    pos = texto.index("[") + 1
    while True:
        pos = _SEPARADOR_JSON.match(texto, pos).end()
        if texto[pos] == "]":
            break
        objeto, fim = decodificador.raw_decode(texto, pos)
        linha = texto.count("\n", 0, pos) + 1
        if not isinstance(objeto, dict):
            info.avisos.append(f"linha {linha}: item não é um objeto JSON; ignorado")
        else:
            registros.append(Registro(linha=linha, dados=objeto))
        pos = fim
    return registros, info
