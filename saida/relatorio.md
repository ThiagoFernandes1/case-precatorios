# Relatório da limpeza

Data de referência (para prazo vencido): 2026-11-24. Gerado por `python -m limpeza`. Os arquivos de origem não são alterados; o hash abaixo identifica exatamente qual versão foi lida.

## Arquivos lidos

| arquivo | sha256 (início) | codificação | separador | fim de linha |
|---|---|---|---|---|
| tribunal.csv | `0ce8aab43966f28b` | cp1252 | ; | CRLF |
| hub.csv | `75fcf6e07dc05078` | utf-8 | , | LF |
| apresentacoes.json | `0da8be22859b58fa` | utf-8 | - | CRLF |
| pagamentos.json | `83e761b199bfea34` | utf-8 | - | CRLF |

## Resumo

- Registros em pagamentos.json: 13. 5 ok, 2 corrigido, 2 descartado, 4 em duvida.
- Total pago confirmado: R$ 18.700,50. Em dúvida (fora do total): R$ 15.500,00, mais os eventos em dúvida sem valor ou sem processo listados abaixo.
- Precatórios na base: 6 (4 nas duas listas, 1 só no tribunal, 1 só no hub).
- Comparação tribunal x hub: dos 4 precatórios que estão nas duas listas, comparar número e nome do ente exatamente como escritos marca 3 como diferentes. Em 2 a diferença é só de escrita (máscara, acento, caixa). Divergências reais: ente em 0045678-43.2021.5.02.0011; valor de face em 0023456-21.2020.8.26.0053, que a comparação manual não olha.
- Prazos do hub recalculados: 2 (0012345-10.2019.8.26.0053, 0056789-54.2017.4.03.6100).
- Vencidos com saldo em 2026-11-24: 2 (0034567-32.2018.8.26.0405, 0067890-65.2016.8.26.0053).

## Precatórios

| processo | ente | valor de face | apresentado | prazo | prazo no hub | pago | em dúvida | situação |
|---|---|---|---|---|---|---|---|---|
| 0012345-10.2019.8.26.0053 | Município de São Paulo | R$ 45.000,00 | 2025-04-02 | 2026-12-31 | 2027-12-31 | R$ 2.500,50 | R$ 15.500,00 | em_duvida |
| 0023456-21.2020.8.26.0053 | Município de São Paulo | R$ 30.000,00 | 2025-04-03 | 2027-12-31 | 2027-12-31 | R$ 9.200,00 | R$ 0,00 | em_duvida |
| 0034567-32.2018.8.26.0405 | Estado de São Paulo | R$ 12.500,00 | 2024-02-29 | 2025-12-31 (vencido) | 2025-12-31 | R$ 0,00 | R$ 0,00 | ok |
| 0045678-43.2021.5.02.0011 | União | R$ 9.800,00 | 2025-04-02 | 2026-12-31 | 2026-12-31 | R$ 3.000,00 | R$ 0,00 | em_duvida |
| 0056789-54.2017.4.03.6100 | Estado de São Paulo | R$ 22.000,00 | 2025-04-02 | 2026-12-31 | 2027-12-31 | R$ 0,00 | R$ 0,00 | em_duvida |
| 0067890-65.2016.8.26.0053 | Município de São Paulo | R$ 7.000,00 | 2023-12-31 | 2025-12-31 (vencido) | - | R$ 4.000,00 | R$ 0,00 | em_duvida |

**0012345-10.2019.8.26.0053**

- prazo recalculado: hub dizia 2027-12-31, o correto é 2026-12-31; apresentado exatamente em 2 de abril, que está dentro do "até 2 de abril"
- evento ev-001 (15500.00) em dúvida, fora do total pago

**0023456-21.2020.8.26.0053**

- valor de face diverge: tribunal 30000.00 (tribunal.csv linha 3), hub 31000.00 (hub.csv linha 3); mantido o do tribunal
- evento ev-004 em dúvida: valor ausente (null)

**0045678-43.2021.5.02.0011**

- ente diverge: tribunal 'União' (tribunal.csv linha 5), hub 'Município de Santos' (hub.csv linha 5)

**0056789-54.2017.4.03.6100**

- está no hub mas não na lista do tribunal: pode ter sido pago, cancelado ou ser de outra lista
- apresentação veio como instante (2025-04-03T01:00:00Z); no horário de Brasília o dia é 2025-04-02
- prazo recalculado: hub dizia 2027-12-31, o correto é 2026-12-31; o hub parece ter usado a data escrita no campo, que está em UTC, e não o dia em Brasília
- evento ev-009 em dúvida: valor negativo (-200.00) em evento do tipo 'pagamento': pode ser um estorno lançado com o tipo errado, mas não há como confirmar

**0067890-65.2016.8.26.0053**

- está na lista do tribunal mas não no hub: a operação não enxerga este precatório

## Pagamentos, registro a registro

| linha | evento | situação | motivo |
|---|---|---|---|
| 2 | ev-001 | descartado | versão antiga (atualizado_em 2025-03-10T10:00:00-03:00, valor 15000.0); substituída pela da linha 66 (atualizado_em 2025-03-11T09:00:00-03:00, valor 15500.0) |
| 10 | ev-002 | corrigido | valor veio como texto no formato brasileiro ('2.500,50'); lido como 2500.50; data '10/04/2025' lida como 2025-04-10; a leitura 2025-10-04 seria depois da última atualização do registro (2025-04-10) |
| 18 | ev-003 | ok | importado sem alteração |
| 26 | ev-002 | descartado | cópia idêntica do registro da linha 10 |
| 34 | ev-004 | em_duvida | valor ausente (null) |
| 42 | ev-005 | corrigido | processo sem máscara (00234562120208260053) normalizado |
| 50 | ev-006 | ok | importado sem alteração |
| 58 | ev-007 | ok | tipo 'estorno' não está na documentação (que diz 'sempre pagamento'); subtraído do total, como o banco já prevê |
| 66 | ev-001 | em_duvida | pagamento em 2025-03-10, antes da apresentação do precatório (2025-04-02) |
| 74 | ev-008 | ok | importado sem alteração |
| 82 | ev-009 | em_duvida | valor negativo (-200.00) em evento do tipo 'pagamento': pode ser um estorno lançado com o tipo errado, mas não há como confirmar |
| 90 | ev-010 | em_duvida | processo vazio; valor 750 sem precatório para atribuir |
| 98 | ev-011 | ok | importado sem alteração |

## Ajustes nos cadastros

- hub.csv, linha 3: 0023456-21.2020.8.26.0053: corrigido. processo gravado sem máscara (00234562120208260053); normalizado para casar com as outras fontes

## Avisos sobre os arquivos

- todos: 6 de 6 processos têm DV CNJ inválido. Esperado se os números são fictícios; em produção isso deveria barrar o registro.
- tribunal.csv: codificação cp1252; a documentação diz UTF-8
- tribunal.csv: separador ';'; a documentação diz vírgula
- tribunal.csv: valor_face com vírgula decimal nas linhas [2, 3, 4, 5, 6]; a documentação diz ponto
- pagamentos.json: valor em texto nas linhas [10, 26]; a documentação diz número
- pagamentos.json: data_pagamento fora de AAAA-MM-DD nas linhas [10, 26]
- pagamentos.json: tipo diferente de 'pagamento' nas linhas [58]; a documentação diz que é sempre 'pagamento'
- pagamentos.json: evento_id repetido: ev-001, ev-002; a documentação diz que é único
- pagamentos.json: os eventos vão de 2025-02-20 a 2025-08-10; o arquivo deveria trazer só os últimos 7 dias
- apresentacoes.json: arquivo não aparece na documentação do tribunal
- apresentacoes.json: apresentado_em mistura data pura e data com hora e fuso (com hora nas linhas [14, 18])
