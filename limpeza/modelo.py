from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

# Situações de um registro, da melhor para a pior. Um registro com várias ocorrências
# fica com a pior delas.
OK = "ok"
CORRIGIDO = "corrigido"  # entrou na base depois de uma correção com uma única leitura possível
DESCARTADO = "descartado"  # tenho certeza de que não deve contar (duplicata, versão antiga)
EM_DUVIDA = "em_duvida"  # não sei; precisa de alguém do tribunal ou da operação
AVISO = "aviso"  # observação sobre o arquivo inteiro, não sobre um registro

_ORDEM = {OK: 0, CORRIGIDO: 1, DESCARTADO: 2, EM_DUVIDA: 3}


def pior(a: str, b: str) -> str:
    return a if _ORDEM[a] >= _ORDEM[b] else b


@dataclass
class Ocorrencia:
    """Uma linha do relatório: o que aconteceu com um registro de origem e por quê."""

    arquivo: str
    linha: int | None
    chave: str
    situacao: str
    motivo: str


@dataclass
class Precatorio:
    processo: str  # 20 dígitos
    ente_devedor: str | None = None
    valor_face: Decimal | None = None
    apresentado_em: date | None = None
    prazo_pagamento: date | None = None
    no_tribunal: bool = False
    no_hub: bool = False
    ente_hub: str | None = None
    valor_face_hub: Decimal | None = None
    prazo_hub: str | None = None
    total_pago: Decimal = Decimal("0.00")
    valor_em_duvida: Decimal = Decimal("0.00")
    situacao: str = OK
    observacoes: list[str] = field(default_factory=list)
    # Diferenças entre tribunal e hub que a comparação exata acusaria, mas não são divergência.
    diferencas_de_forma: list[str] = field(default_factory=list)

    def marcar(self, situacao: str, observacao: str) -> None:
        self.situacao = pior(self.situacao, situacao)
        self.observacoes.append(observacao)


@dataclass
class Pagamento:
    evento_id: str
    processo: str
    tipo: str
    valor: Decimal  # sempre positivo, como no banco
    data_pagamento: date
    atualizado_em: datetime
    arquivo: str
    linha: int
    situacao: str = OK
    observacoes: list[str] = field(default_factory=list)

    @property
    def valor_liquido(self) -> Decimal:
        return -self.valor if self.tipo == "estorno" else self.valor

    def marcar(self, situacao: str, observacao: str) -> None:
        self.situacao = pior(self.situacao, situacao)
        self.observacoes.append(observacao)
