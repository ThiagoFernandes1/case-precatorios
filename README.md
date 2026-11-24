# Case: conciliação de precatórios

A análise completa (diagnóstico, prevenção e dúvidas) está em [ANALISE.md](ANALISE.md).
O resultado da limpeza já gerado está em [saida/relatorio.md](saida/relatorio.md).

## Como rodar

Precisa de Python 3.10 ou mais recente (testado em 3.10 e 3.11).

```bash
python -m venv .venv
source .venv/bin/activate          # no Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt

python -m limpeza                  # lê recebido/dados e grava em saida/
python -m pytest                   # testes
```

`python -m limpeza --help` mostra as opções. A data de referência (usada só para marcar
prazo vencido) é hoje por padrão; a saída versionada foi gerada com
`--data-referencia 2026-11-24`.

A única dependência é `tzdata`, a base de fusos horários, que no Windows não vem com o
sistema. Ela é usada para converter a data de apresentação para o horário de Brasília.

## O que tem aqui

```
recebido/           arquivos do case exatamente como vieram (o git não converte fim de linha)
limpeza/            programa de limpeza
  leitura.py          lê CSV e JSON descobrindo encoding e separador
  normalizacao.py     processo CNJ, valor, data, fuso e prazo
  precatorios.py      junta tribunal, hub e apresentações
  pagamentos.py       versões, duplicatas, estornos e validação dos eventos
  relatorio.py        escreve saida/
tests/              testes das regras de maior risco e um teste de ponta a ponta
saida/              base limpa e relatório gerados
sql/prevencao.sql   mudanças no banco propostas na análise
```

Arquivos de saída:

- `precatorios.csv`: um precatório por linha, com prazo recalculado, total pago, valor em
  dúvida, saldo e o que diverge entre tribunal e hub.
- `pagamentos.csv`: um evento por `evento_id`, indicando se conta no total.
- `decisoes.csv`: cada registro de pagamento (com arquivo e linha) e cada precatório, com a
  situação (ok, corrigido, descartado, em dúvida) e o motivo, mais os avisos sobre o formato
  dos arquivos.
- `relatorio.md`: o mesmo conteúdo em texto, para a operação ler.

## Uso de IA

Usei o Claude Code durante o case: para inspecionar os arquivos (encoding, bytes, fim de
linha), escrever o código, os testes e o SQL e redigir os textos.

Como o que a IA produziu foi conferido:

- Os totais por processo e os prazos dos seis precatórios foram calculados à parte, antes de
  existir código, e depois comparados com a saída do programa. O teste de ponta a ponta
  (`tests/test_ponta_a_ponta.py`) trava esses números.
- As linhas citadas no ANALISE.md foram conferidas contra os arquivos em `recebido/`.
- Foi um teste que corrigiu uma conta feita de cabeça: o prazo do 0067890 é 2025, não 2024.
- A afirmação de que nenhuma regra única explica os prazos do hub foi testada com um script
  que roda as oito combinações de regra possíveis contra o `hub.csv`.
- O `sql/prevencao.sql` foi rodado num PostgreSQL 16 local, depois do `schema.sql` recebido, com
  os eventos do case: reimportação, versão antiga chegando depois, estorno, número com
  máscara. Foi assim que apareceu o problema da constraint `NOT VALID`, que está explicado
  no SQL.
- Os testes e a limpeza foram rodados num clone limpo do repositório em Python 3.10, e a
  saída gerada foi idêntica à versionada.
- Um teste de ponta a ponta falhou logo depois de um commit (dá para ver no histórico): o
  teste estava errado, não o código, e a correção está no commit seguinte.
