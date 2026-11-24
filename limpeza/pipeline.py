from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from . import pagamentos as mod_pagamentos
from . import precatorios as mod_precatorios
from .leitura import Arquivo, ler_csv, ler_json_lista
from .modelo import AVISO, Ocorrencia, Pagamento, Precatorio

COLUNAS_TRIBUNAL = ["numero_processo", "ente_devedor", "valor_face"]
COLUNAS_HUB = ["processo", "ente", "valor_face", "apresentado_em", "prazo_pagamento"]


@dataclass
class Resultado:
    data_referencia: date
    arquivos: list[Arquivo]
    precatorios: dict[str, Precatorio]
    pagamentos: list[Pagamento]
    ocorrencias: list[Ocorrencia]
    avisos: list[Ocorrencia]


def executar(entrada: Path, data_referencia: date) -> Resultado:
    tribunal, info_trib = ler_csv(entrada / "tribunal.csv", COLUNAS_TRIBUNAL)
    hub, info_hub = ler_csv(entrada / "hub.csv", COLUNAS_HUB)
    apresentacoes, info_apres = ler_json_lista(entrada / "apresentacoes.json")
    eventos, info_pag = ler_json_lista(entrada / "pagamentos.json")

    precatorios, oc_precatorios = mod_precatorios.consolidar(tribunal, hub, apresentacoes)
    pagamentos, oc_pagamentos = mod_pagamentos.processar(eventos, precatorios)

    avisos = [o for o in oc_precatorios if o.situacao == AVISO]
    avisos += _avisos_de_formato(info_trib, tribunal, eventos, apresentacoes)
    for info in (info_trib, info_hub, info_apres, info_pag):
        avisos += [Ocorrencia(info.caminho.name, None, "leitura", AVISO, a) for a in info.avisos]

    return Resultado(
        data_referencia=data_referencia,
        arquivos=[info_trib, info_hub, info_apres, info_pag],
        precatorios=precatorios,
        pagamentos=pagamentos,
        ocorrencias=[o for o in oc_precatorios if o.situacao != AVISO] + oc_pagamentos,
        avisos=avisos,
    )


def _avisos_de_formato(info_trib, tribunal, eventos, apresentacoes) -> list[Ocorrencia]:
    """Diferenças entre o que veio e o que a DOCUMENTACAO_TRIBUNAL.md (v2.1) promete."""
    avisos = []

    def aviso(arquivo, texto):
        avisos.append(Ocorrencia(arquivo, None, "documentação", AVISO, texto))

    if info_trib.encoding != "utf-8":
        aviso("tribunal.csv", f"codificação {info_trib.encoding}; a documentação diz UTF-8")
    if info_trib.delimitador != ",":
        aviso("tribunal.csv", f"separador '{info_trib.delimitador}'; a documentação diz vírgula")
    com_virgula = [r.linha for r in tribunal if "," in (r.dados.get("valor_face") or "")]
    if com_virgula:
        aviso("tribunal.csv", f"valor_face com vírgula decimal nas linhas {com_virgula}; a documentação diz ponto")

    valores_texto = [r.linha for r in eventos if isinstance(r.dados.get("valor"), str)]
    if valores_texto:
        aviso("pagamentos.json", f"valor em texto nas linhas {valores_texto}; a documentação diz número")
    datas_fora = [r.linha for r in eventos
                  if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(r.dados.get("data_pagamento") or ""))]
    if datas_fora:
        aviso("pagamentos.json", f"data_pagamento fora de AAAA-MM-DD nas linhas {datas_fora}")
    estornos = [r.linha for r in eventos if r.dados.get("tipo") != "pagamento"]
    if estornos:
        aviso("pagamentos.json", f"tipo diferente de 'pagamento' nas linhas {estornos}; a documentação diz "
                                 "que é sempre 'pagamento'")
    ids = [str(r.dados.get("evento_id")) for r in eventos]
    repetidos = sorted({i for i in ids if ids.count(i) > 1})
    if repetidos:
        aviso("pagamentos.json", f"evento_id repetido: {', '.join(repetidos)}; a documentação diz que é único")
    datas = sorted(str(r.dados.get("data_pagamento")) for r in eventos if r.dados.get("data_pagamento"))
    if datas:
        aviso("pagamentos.json", f"os eventos vão de {min(datas, key=_iso)} a {max(datas, key=_iso)}; o arquivo "
                                 "deveria trazer só os últimos 7 dias")

    com_hora = [r.linha for r in apresentacoes if "T" in str(r.dados.get("apresentado_em"))]
    aviso("apresentacoes.json", "arquivo não aparece na documentação do tribunal")
    if com_hora:
        aviso("apresentacoes.json", f"apresentado_em mistura data pura e data com hora e fuso (com hora nas linhas "
                                    f"{com_hora})")
    return avisos


def _iso(texto: str) -> str:
    encontrado = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", texto)
    return f"{encontrado[3]}-{encontrado[2]}-{encontrado[1]}" if encontrado else texto
