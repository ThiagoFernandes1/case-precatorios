# Análise: por que os números não batem com os do tribunal

Este documento tem quatro partes: diagnóstico, como a limpeza decide cada caso, prevenção e
dúvidas. As linhas citadas são dos arquivos em `recebido/`, que são cópia exata do que veio.
O resultado da limpeza está em `saida/relatorio.md`.

Data de referência usada para falar de prazo: 24/11/2026.

## Resumo

Os números não batem por dois erros que puxam em sentidos opostos, e por isso ninguém
consegue apontar onde está o problema. A importação soma a mais (o mesmo evento entra mais de uma vez e o estorno
entra como pagamento) e soma a menos (evento que não passa na validação some sem aviso). Os
dois erros se misturam no mesmo total, e o total por processo fica errado nos dois sentidos.

Fazendo a conta para este arquivo de pagamentos, com as premissas descritas no item 1:

| processo | o que o script atual provavelmente mostra | base limpa | fora do total, em dúvida |
|---|---|---|---|
| 0012345-10.2019.8.26.0053 | 30.500,00 (ev-001 duas vezes, ev-002 recusado) | 2.500,50 | 15.500,00 (ev-001) |
| 0023456-21.2020.8.26.0053 | 1.200,00 (só o ev-005 casa com o número do hub) | 9.200,00 | ev-004, sem valor |
| 0034567-32.2018.8.26.0405 | 10.000,00 (estorno somado) | 0,00 | |
| 0045678-43.2021.5.02.0011 | 3.000,00 | 3.000,00 | |
| 0056789-54.2017.4.03.6100 | 0,00 (o -200 é barrado pelo CHECK) | 0,00 | ev-009, -200 |
| 0067890-65.2016.8.26.0053 | não existe no hub | 4.000,00 | |
| sem processo | | | ev-010, 750 |
| total | 44.700,00 | 18.700,50 | 15.500,00 + 3 eventos |

Ao lado do dinheiro, há um problema de prioridade: dois precatórios que vencem em
31/12/2026, daqui a cinco semanas, aparecem no hub com prazo em 2027. E um precatório
vencido desde 2025 nem existe no hub.

### Como os problemas se ligam

```
Documentação desatualizada (9) ─┐
                                ├─> importador aceita/rejeita errado ─┬─> soma a mais (1, 2)
Importador sem idempotência ────┘                                     └─> soma a menos em silêncio (4)

Processo sem forma única (6) ──> evento não acha o precatório (4); conferência acusa diferença falsa (7)
Excel no meio da conferência ──> arquivo do tribunal alterado; comparação exata não serve (7)
Data com e sem fuso + regra de corte ──> prazo errado (3)
Hub e tribunal sem reconciliação ──> carteira diferente (5)
```

## 1. Diagnóstico

Ordenei pelo impacto no negócio: primeiro o que muda dinheiro e prazo, depois o que esconde
os erros, por último o que é causa de fundo.

### 1.1 A importação soma de novo o que já foi importado

Causa: é a principal razão de o total pago ficar maior que o do tribunal. É agravado por
1.9, porque a documentação não diz que um evento pode chegar em mais de uma versão.

Evidência:
- `pagamentos.json` linhas 10 e 26: o evento `ev-002` aparece duas vezes, idêntico.
- `pagamentos.json` linhas 2 e 66: o evento `ev-001` aparece duas vezes com valores
  diferentes, 15.000,00 (atualizado em 10/03/2025) e 15.500,00 (atualizado em 11/03/2025).
  Ou seja, o tribunal reenvia o evento quando corrige, com o mesmo `evento_id`.
- Fluxo, passo 1: cada arquivo diário traz os últimos 7 dias. O mesmo evento chega em até
  7 arquivos seguidos.
- Fluxo, passo 2: o script soma cada valor ao total, e quando falha no meio o operador roda
  de novo o mesmo arquivo. A primeira metade é somada duas vezes.
- `schema.sql`: `pagamento.evento_id` não é único e não existe coluna para `atualizado_em`.
  Nada no banco impede a duplicata, e não dá para saber qual versão de um evento é a última.

Impacto: o total pago fica maior que o real e o saldo a receber fica menor. Um precatório
pode parecer quase quitado e sair da prioridade. Só neste arquivo, o processo 0012345 recebe
30.500,00 quando o valor certo (se o ev-001 estiver certo) é 18.000,50. Em produção, com as
janelas de 7 dias se sobrepondo, o mesmo pagamento pode ter sido somado até sete vezes.

Premissa da tabela do resumo: suponho que o script soma todo evento cujo valor é número e
cujo processo bate exatamente com o texto gravado no sistema, ignora o `tipo` e pula o que
der erro. Não vi o script; se ele já deduplicar por `evento_id`, a parte de soma a mais cai,
mas a de versões continua (a primeira versão do ev-001 fica, ou as duas).

### 1.2 Estorno entra como pagamento

Consequência de 1.9 (a documentação diz que o tipo é sempre "pagamento") e do script que
"soma cada valor". É causa de total pago inflado e de saldo subestimado.

Evidência:
- `pagamentos.json` linhas 50 e 58: `ev-006` é um pagamento de 5.000,00 e `ev-007` um
  estorno de 5.000,00, um dia depois, no mesmo processo 0034567.
- `DOCUMENTACAO_TRIBUNAL.md`: o campo `tipo` é "Sempre pagamento".
- `schema.sql`: a tabela aceita `tipo = 'estorno'` com `valor > 0`. O sinal tem que vir do
  tipo, mas o fluxo descreve um script que só soma.

Impacto: pela premissa do 1.1, o processo 0034567 aparece com 10.000,00 pagos quando o
líquido é zero. É o caso mais grave da carteira: o prazo dele venceu em 31/12/2025, o saldo real é o valor de face
inteiro (12.500,00) e o sistema mostra 80% pago.

### 1.3 Prazo de pagamento errado, sempre um ano para frente

Causa de priorização errada. É consequência de duas falhas no cálculo e da data de
apresentação vir em formatos misturados (1.9).

Evidência, em `hub.csv` (o prazo certo está recalculado em `saida/precatorios.csv`):

| linha | processo | apresentado_em | prazo no hub | prazo certo | por quê |
|---|---|---|---|---|---|
| 2 | 0012345 | 2025-04-02 | 2027-12-31 | 2026-12-31 | "até 2 de abril" inclui o dia 2 |
| 6 | 0056789 | 2025-04-03T01:00:00Z | 2027-12-31 | 2026-12-31 | 01h em UTC é 22h do dia 2 em Brasília |
| 5 | 0045678 | 2025-04-02T23:30:00-03:00 | 2026-12-31 | 2026-12-31 | certo (em UTC já seria dia 3) |

Os outros dois precatórios do hub estão certos.

Impacto: os dois precatórios vencem em 31/12/2026, daqui a cinco semanas, e a equipe acha
que tem até o fim de 2027. Somam 67.000,00 de valor de face.

Observação: testei oito combinações de regra (data como está escrita, em UTC ou em
Brasília; corte com "antes de" ou "até" 2 de abril) e nenhuma reproduz os cinco prazos do
hub. A mais próxima, "data como está escrita, antes de 2 de abril", acerta quatro e erra
justamente o 0045678. Isso sugere que o cálculo mudou ao longo do tempo ou que algum prazo
foi editado à mão. Está nas dúvidas.

### 1.4 Evento que não entra some sem aviso

Causa: é o que faz "ninguém saber onde está o erro", e é o que transforma 1.6 e 1.8 em
dinheiro faltando no total.

Evidência (fluxo, passo 5: "o script ignora e segue"). Eventos deste arquivo que o banco
atual ou uma validação simples recusaria:

| linha | evento | por que seria recusado | valor |
|---|---|---|---|
| 10 | ev-002 | valor em texto `"2.500,50"` e data `10/04/2025` | 2.500,50 |
| 18 | ev-003 | processo com máscara não bate, por comparação exata, com o hub, que grava 0023456 sem máscara | 8.000,00 |
| 34 | ev-004 | valor `null` | ? |
| 82 | ev-009 | valor -200, barrado pelo `CHECK (valor > 0)` | -200,00 |
| 90 | ev-010 | processo vazio | 750,00 |
| 98 | ev-011 | processo 0067890 não existe no hub (falha a chave estrangeira) | 4.000,00 |

Impacto: até 6 dos 11 eventos distintos podem estar sumindo sem deixar rastro. Quando o
total não bate, não há lista do que ficou de fora para conferir. Isso faz o erro de 1.1 (soma a mais)
se misturar com este (soma a menos) sem ninguém conseguir separar um do outro.

### 1.5 Tribunal e hub não têm a mesma carteira

Consequência de a conferência semanal não funcionar (1.7). É causa de pagamento recusado
(1.4) e de precatório vencido fora da priorização.

Evidência:
- `tribunal.csv` linha 6: 0067890-65.2016.8.26.0053, Município de São Paulo, 7.000,00,
  não está no `hub.csv`. Pelo `apresentacoes.json` (linha 22) foi apresentado em
  31/12/2023, então venceu em 31/12/2025. E tem pagamento: `ev-011`, 4.000,00.
- `hub.csv` linha 6: 0056789-54.2017.4.03.6100, Estado de São Paulo, 22.000,00, não está no
  `tribunal.csv`.

Impacto: o 0067890 está vencido, com saldo de 3.000,00, e a equipe não o enxerga. O
pagamento dele (`ev-011`) não tem onde entrar e some sem aviso. O 0056789 pode ter sido pago, cancelado ou pertencer a
outra lista (é da Justiça Federal, 4.03, e os outros são do TJSP e do TRT2); sem saber, a
equipe pode estar priorizando algo que não existe mais.

### 1.6 O número do processo não tem uma forma única

Causa de 1.4 (evento não acha o precatório) e de 1.7 (falsa divergência).

Evidência:
- `hub.csv` linha 3: `00234562120208260053`, sem máscara; as outras linhas têm máscara.
- `pagamentos.json` linha 42: `ev-005` usa o mesmo processo sem máscara; o `ev-003` (linha
  18) usa com máscara. São o mesmo precatório.
- `schema.sql`: `numero_processo CHAR(20)`. O número com máscara tem 25 caracteres e não
  cabe; só cabem os 20 dígitos. Mesmo assim o `hub.csv` exporta quatro dos cinco com máscara.
  Ou o esquema que recebi não é o que está em produção, ou a exportação formata uns e não
  outros. Está nas dúvidas.
- `CHAR` completa com espaços, e nada impede letra ou número truncado.

Impacto: dependendo de como foi gravado, um pagamento correto não encontra o precatório e
some (1.4). No caso do 0023456, o pagamento de 8.000,00 se perde e o de 1.200,00 entra.

### 1.7 A conferência semanal gera alarme falso e esconde divergência real

Consequência do Excel no meio do fluxo e de 1.6. Causa de 1.5 continuar sem solução.

Evidência:
- `tribunal.csv` está em cp1252, separado por `;`, com valores `45.000,00` e fim de linha
  CRLF. A documentação diz UTF-8, vírgula e ponto decimal. É o formato típico de um CSV
  salvo pelo Excel em português. Hipótese: o arquivo que está na pasta não é
  o que o tribunal mandou, e sim o que o operador salvou (passo 3 do fluxo). Se for isso, o
  original se perdeu.
- Comparando nome do ente e número do processo exatamente como escritos, 3 dos 4
  precatórios que estão nas duas listas aparecem como diferentes:
  - 0012345: `Município de São Paulo` contra `MUNICIPIO DE SAO PAULO` (só caixa e acento)
  - 0023456: número com e sem máscara (só formato)
  - 0045678: `União` contra `Município de Santos` (divergência real)
- A comparação manual não olha o valor de face, e o 0023456 tem 30.000,00 no tribunal e
  31.000,00 no hub (`tribunal.csv` linha 3, `hub.csv` linha 3).

Impacto: com 2 alarmes falsos em 3, a conferência perde credibilidade e as duas divergências
reais (ente do 0045678 e valor do 0023456) ficam no meio do ruído. Ente errado muda o regime
de pagamento e com quem negociar. Além disso, abrir e salvar no Excel tem um risco que não
apareceu aqui mas é comum: um número de processo só com dígitos, como o do 0023456, vira
`2,34562E+16`, perde os zeros da frente e, ao salvar, os últimos dígitos.

### 1.8 Eventos que não fecham com o resto dos dados

Causa: são erros na origem, no tribunal, e viram parte de 1.4 (somem do total). Precisam
de resposta do tribunal, não de correção nossa.

Evidência:
- `ev-001` (linha 66): pagamento em 10/03/2025 de um precatório apresentado em 02/04/2025
  (`apresentacoes.json` linha 2). Pagamento antes da apresentação não deveria existir.
  Pode estar errada a data do pagamento, a data da apresentação, ou o processo.
- `ev-009` (linha 82): valor -200 com tipo `pagamento`. Pode ser um estorno com tipo errado,
  mas não há pagamento anterior desse processo para estornar.
- `ev-004` (linha 34): valor `null`.
- `ev-010` (linha 90): processo vazio.

Impacto: 15.500,00 cujo destino não é seguro, mais três eventos sem como atribuir. A limpeza
deixa esses valores fora do total e lista cada um.

### 1.9 A documentação do tribunal não descreve os arquivos que chegam

Causa de fundo de 1.1, 1.2 e de boa parte de 1.4: o script foi escrito seguindo a
documentação.

| documentação diz | o que veio | onde |
|---|---|---|
| `evento_id` é identificador único | repete, com e sem alteração | pagamentos.json linhas 2/66, 10/26 |
| `tipo` é sempre "pagamento" | existe "estorno" | linha 58 |
| `valor` é número com ponto | texto `"2.500,50"`, `null`, negativo | linhas 10, 34, 82 |
| `data_pagamento` é AAAA-MM-DD | `10/04/2025` | linha 10 |
| `processo` no formato CNJ | sem máscara, vazio | linhas 42, 90 |
| arquivo traz os últimos 7 dias | eventos de 20/02/2025 a 10/08/2025 | todo o arquivo |
| tribunal.csv em UTF-8, vírgula, ponto | cp1252, ponto e vírgula, vírgula decimal | todo o arquivo (ver 1.7) |
| não fala de `apresentacoes.json` | o arquivo existe e mistura data pura com data e hora com fuso | linhas 14 e 18 (o hub.csv repete isso nas linhas 5 e 6) |

Também não diz o que significa `atualizado_em` (se a versão mais nova substitui a anterior),
como o estorno aponta o pagamento que estorna, nem se a lista de precatórios é completa ou
parcial.

Além disso, os seis números de processo têm dígito verificador CNJ inválido. Como o
enunciado diz que os processos são fictícios, tratei isso como aviso e não como erro.

## 2. Limpeza

Código em `limpeza/`, testes em `tests/`, saída em `saida/`. Como rodar está no README.

Cada registro de pagamento e cada precatório termina em uma de quatro situações, e todas
ficam em `saida/decisoes.csv` com arquivo, linha (quando se aplica) e motivo:

- ok: entrou como veio.
- corrigido: entrou depois de uma correção que só tinha uma leitura possível.
- descartado: tenho certeza de que não deve contar (cópia idêntica, versão substituída).
- em dúvida: não sei. Não entra no total pago, mas aparece no relatório com o valor ao lado,
  para alguém resolver.

A linha que separei entre corrigir e duvidar:

| caso | decisão | por quê |
|---|---|---|
| processo sem máscara | corrige | 20 dígitos só têm um jeito de virar máscara |
| processo com máscara parcial ou dígitos a menos | dúvida | completar zeros pode juntar dois processos |
| valor `"2.500,50"` | corrige | só existe uma leitura |
| valor `"2.500"` | dúvida | pode ser dois mil e quinhentos ou dois e meio |
| data `10/04/2025` | corrige para 10/04 | 4 de outubro seria depois da última atualização do registro (10/04) |
| data `03/04/2025` com atualização em maio | dúvida | as duas leituras são possíveis |
| mesmo `evento_id`, conteúdo igual | descarta a cópia | |
| mesmo `evento_id`, conteúdo diferente | vale o maior `atualizado_em` | é a única regra que explica o ev-001; está nas dúvidas para o tribunal confirmar |
| mesmo `evento_id`, mesmo `atualizado_em`, conteúdo diferente | dúvida | não há como escolher |
| estorno | subtrai | |
| estorno maior que o pago até ali | dúvida | |
| valor nulo, zero ou negativo | dúvida | |
| processo vazio ou desconhecido | dúvida | |
| pagamento antes da apresentação ou depois do `atualizado_em` | dúvida | |
| ente igual sem acento e caixa | mesmo ente | |
| ente diferente, valor de face diferente | dúvida, mantém o do tribunal e mostra o do hub | o tribunal emite o precatório |
| precatório em só uma das listas | entra na base em dúvida | sumir com ele é pior que mostrar |
| apresentação com hora e fuso | converte para o dia em Brasília | o tribunal conta o dia no horário local (suposição, está nas dúvidas) |

Algumas decisões de implementação que vale explicar:

- Dinheiro nunca passa por `float`. O JSON é lido com `Decimal` direto do texto.
- O dia da apresentação usa `America/Sao_Paulo` com a base de fusos do sistema, e não um
  "UTC-3" fixo. Até 2019 o Brasil tinha horário de verão; perto da virada do ano isso muda o
  dia e, portanto, o ano do prazo. Há um teste para isso.
- O resultado depende do conjunto de eventos e não de quantas vezes cada um aparece. O teste
  principal processa o mesmo arquivo uma, duas e sete vezes e confere o mesmo total.
- O programa se recusa a gravar dentro da pasta de entrada, e o teste de ponta a ponta
  confere o hash dos originais antes e depois. O relatório também grava o hash de cada
  arquivo lido, para saber exatamente qual versão foi processada.

## 3. Prevenção

### No processo

1. Guardar o arquivo do tribunal como veio, antes de qualquer pessoa abrir: pasta só de
   leitura ou bucket, com o hash no nome. Ninguém abre o CSV no Excel para conferir.
2. A conferência semanal passa a ser um programa (a própria limpeza serve de base), com
   chave normalizada, olhando também valor de face e data de apresentação. A saída é uma
   lista curta de divergências reais, não uma comparação visual.
3. Toda importação termina com um resumo enviado para a operação: quantos entraram, quantos
   foram descartados como duplicata e quantos estão em dúvida, com o motivo. Dúvida tem
   dono e prazo para ser resolvida.
4. Pedir ao tribunal a versão 2.2 da documentação cobrindo estorno, versões de evento,
   fuso das datas, `apresentacoes.json` e se a lista de precatórios é completa. Melhor ainda
   se vier acompanhada de um JSON Schema, para o arquivo ser validado na entrada.

### No script de importação

1. Idempotente: grava por `evento_id` com upsert, e só substitui se o `atualizado_em` novo
   for maior. Reimportar o mesmo arquivo, ou receber o mesmo evento em sete janelas, não
   muda nada.
2. Uma transação por arquivo. Se falhar no meio, nada fica gravado, e rodar de novo é seguro.
3. Registra o arquivo como lote, identificado pelo hash. O mesmo arquivo não entra duas vezes.
4. Nunca "ignora e segue". Todo registro recebido é gravado com a situação e o motivo, e o
   que não entra fica em quarentena até alguém resolver.
5. Não acumula total pago. O total é calculado a partir dos eventos, então corrigir um
   evento corrige o total.
6. Usa as funções de normalização da limpeza (processo, valor, data, fuso), que já têm teste.

### No banco

O SQL está em `sql/prevencao.sql`, testado num PostgreSQL 16 local a partir do `schema.sql`
recebido. Resumo:

- `numero_processo` vira `VARCHAR(20)` com `CHECK` de 20 dígitos; a máscara vira função
  (`cnj_formatado`). Há uma função de dígito verificador; a constraint dela fica para depois
  de a base estar limpa, porque no PostgreSQL até uma constraint `NOT VALID` trava UPDATE de
  linha antiga (descobri isso testando).
- `apresentado_em DATE` e `prazo_pagamento` como coluna gerada, com a regra num lugar só.
- `lote_importacao` com `sha256` único e `registro_recebido` com tudo que chegou e o que
  aconteceu, incluindo quem resolveu cada dúvida.
- `pagamento.evento_id` único, coluna `atualizado_em` e o upsert que só aceita versão mais
  nova.
- `precatorio_situacao`, uma view com total pago e saldo, com estorno subtraindo.

A migração apaga a tabela `pagamento` e a recarrega a partir da base limpa. Fiz assim porque
os pagamentos gravados hoje não têm `atualizado_em`, então não há como saber, dentro do
banco, qual cópia de um evento é a certa. Isso tem que ser feito com backup e com a operação
avisada.

### Ordem para colocar em produção

1. Responder as dúvidas da seção 4 que mudam regra (versão de evento, fuso, estorno).
2. Rodar a limpeza sobre o histórico de arquivos recebidos, não só o último.
3. Operação resolve a lista de dúvidas.
4. Migração do banco e recarga dos pagamentos.
5. Liga o importador novo e desliga o antigo.
6. Comparar os totais por processo com o tribunal por algumas semanas antes de confiar.

## 4. Dúvidas

### Para o tribunal

1. O `tribunal.csv` que está na pasta é o arquivo que vocês enviaram? Podem reenviar o
   anexo original? (Quero confirmar se foi o Excel que mudou encoding e separador.)
2. Quando um evento é corrigido, vocês reenviam o mesmo `evento_id` com `atualizado_em`
   novo? A versão nova substitui a anterior por inteiro? Existe outro jeito de cancelar um
   evento além do estorno?
3. `ev-001`: o valor certo é 15.000,00 ou 15.500,00? E como há pagamento em 10/03/2025 se o
   precatório 0012345 foi apresentado em 02/04/2025?
4. Como saber qual pagamento um estorno estorna? Poderiam incluir um campo com o
   `evento_id` original?
5. `ev-009`, -200 como pagamento: é um estorno lançado errado?
6. `ev-004` (valor nulo) e `ev-010` (processo vazio): podem reenviar corrigidos?
7. 0045678: o devedor é a União ou o Município de Santos?
8. 0023456: o valor de face é 30.000,00 ou 31.000,00?
9. A lista de precatórios é completa ou só traz o que mudou? Por que o 0056789 (TRF3) não
   está nela? Ela cobre TJSP, TRT2 e TRF3 juntos?
10. `apresentacoes.json` é de vocês? Em que fuso está a data de apresentação, e por que às
    vezes vem só a data e às vezes data e hora?
11. O arquivo diário deveria trazer 7 dias, mas este traz eventos de fevereiro a agosto de
    2025. Qual é a janela de fato?

### Para a operação

1. Como o hub calcula o prazo hoje? A regra mudou em algum momento, ou algum prazo foi
   editado à mão? Nenhuma regra única explica os cinco prazos do `hub.csv`.
2. O `schema.sql` é o que está em produção? Ele não tem data de apresentação, prazo nem
   total pago, e `CHAR(20)` não aceita o número com máscara que aparece na exportação.
3. Onde fica o total pago, e como o script soma? Ele confere `evento_id` antes de somar?
4. Quando a importação falha no meio, o que já foi gravado fica gravado?
5. Por que o 0067890 não está no hub? Foi removido ou nunca entrou?
6. Algum ente da carteira está no regime especial de pagamento de precatórios? Nesse caso o
   prazo constitucional não é o que define quando ele paga, e a priorização deveria olhar
   outra coisa.
7. A regra de 2 de abril vem da EC 114/2021; antes o corte era 1º de julho. Há na carteira
   precatório apresentado antes da mudança? Se sim, qual regra vocês querem aplicar?
8. O valor pago inclui correção monetária e juros? Se incluir, o total pago pode passar do
   valor de face, e o saldo que a base calcula (valor de face menos total pago) subestima o
   que falta receber. Para priorizar, o certo seria comparar com o valor atualizado.
9. Quem resolve os itens em dúvida e em quanto tempo? Algum relatório ou pessoa depende dos
   números atuais e precisa ser avisado antes da correção?
