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


