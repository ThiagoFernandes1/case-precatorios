-- Mudanças no banco para os problemas descritos em ANALISE.md não voltarem.
-- Aplicar sobre o schema.sql recebido. Testado em PostgreSQL 16.
--
-- Ordem: (1) chave do processo, (2) data de apresentação e prazo, (3) controle de
-- importação e quarentena, (4) pagamento idempotente, (5) total pago calculado.

BEGIN;

-- 1. Número do processo -----------------------------------------------------------------
-- Uma forma só: 20 dígitos. A máscara é formatação de tela, não dado.
-- CHAR(20) completa com espaço e não impede letra nem máscara cortada.
ALTER TABLE precatorio
    ALTER COLUMN numero_processo TYPE VARCHAR(20)
    USING regexp_replace(numero_processo, '\D', '', 'g');

ALTER TABLE precatorio
    ADD CONSTRAINT precatorio_numero_20_digitos CHECK (numero_processo ~ '^[0-9]{20}$');

CREATE FUNCTION cnj_formatado(numero TEXT) RETURNS TEXT
LANGUAGE sql IMMUTABLE STRICT AS $$
    SELECT substr(numero, 1, 7) || '-' || substr(numero, 8, 2) || '.' || substr(numero, 10, 4)
           || '.' || substr(numero, 14, 1) || '.' || substr(numero, 15, 2) || '.' || substr(numero, 17, 4)
$$;

-- Dígito verificador (módulo 97, Resolução CNJ 65/2008).
CREATE FUNCTION cnj_dv_valido(numero TEXT) RETURNS BOOLEAN
LANGUAGE sql IMMUTABLE STRICT AS $$
    SELECT (substr(numero, 1, 7) || substr(numero, 10, 11) || substr(numero, 8, 2))::NUMERIC % 97 = 1
$$;

-- A constraint de DV fica para depois de corrigir a base. Tentei com NOT VALID, mas no
-- PostgreSQL ela também é checada em qualquer UPDATE de linha antiga: um precatório com
-- DV errado não poderia nem receber a data de apresentação. Os números do case são
-- fictícios e todos falhariam. Quando a base estiver limpa:
--   ALTER TABLE precatorio ADD CONSTRAINT precatorio_numero_dv CHECK (cnj_dv_valido(numero_processo));
-- Até lá, o importador manda número com DV inválido para a quarentena.

ALTER TABLE precatorio
    ADD CONSTRAINT precatorio_valor_face_positivo CHECK (valor_face > 0);


-- 2. Apresentação e prazo ---------------------------------------------------------------
-- O dia da apresentação é gravado já no calendário de Brasília (o importador converte
-- instantes com fuso). O instante original fica guardado para auditoria.
ALTER TABLE precatorio ADD COLUMN IF NOT EXISTS apresentado_em DATE;
ALTER TABLE precatorio ADD COLUMN IF NOT EXISTS apresentado_em_original TEXT;

-- O prazo deixa de ser calculado em código e passa a ser derivado pelo banco, num lugar só.
-- "Até 2 de abril" inclui o dia 2.
CREATE FUNCTION prazo_constitucional(apresentacao DATE) RETURNS DATE
LANGUAGE sql IMMUTABLE STRICT AS $$
    SELECT make_date(
        extract(YEAR FROM apresentacao)::INT
            + CASE WHEN apresentacao <= make_date(extract(YEAR FROM apresentacao)::INT, 4, 2) THEN 1 ELSE 2 END,
        12, 31)
$$;

ALTER TABLE precatorio
    ADD COLUMN prazo_pagamento DATE GENERATED ALWAYS AS (prazo_constitucional(apresentado_em)) STORED;


-- 3. Controle de importação e quarentena ------------------------------------------------
-- Cada arquivo recebido vira um lote identificado pelo hash do conteúdo. O mesmo arquivo
-- não entra duas vezes. A importação roda numa transação só: se falhar no meio, nada fica
-- gravado (nem o lote) e rodar de novo é seguro.
CREATE TABLE lote_importacao (
    id           BIGSERIAL   PRIMARY KEY,
    arquivo      TEXT        NOT NULL,
    sha256       CHAR(64)    NOT NULL UNIQUE,
    recebido_em  TIMESTAMPTZ NOT NULL DEFAULT now(),
    registros    INT         NOT NULL,
    aceitos      INT         NOT NULL,
    descartados  INT         NOT NULL,
    em_duvida    INT         NOT NULL
);

-- Todo registro recebido fica guardado como veio, com o que aconteceu com ele.
-- É a tabela que a operação olha para saber o que não entrou e por quê.
CREATE TABLE registro_recebido (
    id             BIGSERIAL   PRIMARY KEY,
    lote_id        BIGINT      NOT NULL REFERENCES lote_importacao (id),
    linha          INT         NOT NULL,
    conteudo       JSONB       NOT NULL,
    situacao       TEXT        NOT NULL CHECK (situacao IN ('ok', 'corrigido', 'descartado', 'em_duvida')),
    motivo         TEXT,
    resolvido_em   TIMESTAMPTZ,
    resolvido_por  TEXT,
    UNIQUE (lote_id, linha),
    CHECK (situacao <> 'em_duvida' OR motivo IS NOT NULL)
);

CREATE INDEX registro_recebido_pendente ON registro_recebido (lote_id)
    WHERE situacao = 'em_duvida' AND resolvido_em IS NULL;


-- 4. Pagamento idempotente ------------------------------------------------------------
-- Pagamentos já gravados não têm atualizado_em e podem estar duplicados; não há como saber
-- qual versão de cada evento é a certa. Por isso a proposta é recarregar a tabela a partir
-- da base limpa (saida/pagamentos.csv) em vez de tentar deduplicar aqui dentro.
-- Antes, para medir o estrago:
--   SELECT evento_id, count(*), sum(valor) FROM pagamento GROUP BY evento_id HAVING count(*) > 1;
TRUNCATE pagamento;

ALTER TABLE pagamento ADD COLUMN atualizado_em TIMESTAMPTZ NOT NULL;
ALTER TABLE pagamento ADD COLUMN lote_id BIGINT REFERENCES lote_importacao (id);
ALTER TABLE pagamento ADD CONSTRAINT pagamento_evento_unico UNIQUE (evento_id);

-- O importador grava assim. Evento repetido não soma de novo; versão mais nova substitui
-- a antiga; versão mais velha que a gravada é ignorada.
--
-- INSERT INTO pagamento (precatorio_id, evento_id, tipo, valor, pago_em, atualizado_em, lote_id)
-- VALUES ($1, $2, $3, $4, $5, $6, $7)
-- ON CONFLICT (evento_id) DO UPDATE
--     SET precatorio_id = EXCLUDED.precatorio_id,
--         tipo          = EXCLUDED.tipo,
--         valor         = EXCLUDED.valor,
--         pago_em       = EXCLUDED.pago_em,
--         atualizado_em = EXCLUDED.atualizado_em,
--         lote_id       = EXCLUDED.lote_id
--     WHERE pagamento.atualizado_em < EXCLUDED.atualizado_em;


-- 5. Total pago calculado, nunca acumulado ----------------------------------------------
-- O script atual soma cada valor num total. Qualquer reimportação ou estorno ignorado
-- deixa esse total errado para sempre. Calculado a partir dos eventos, ele se corrige
-- sozinho quando os eventos são corrigidos.
CREATE VIEW precatorio_situacao AS
SELECT p.id,
       cnj_formatado(p.numero_processo)                                    AS numero_processo,
       p.ente_devedor,
       p.valor_face,
       p.apresentado_em,
       p.prazo_pagamento,
       coalesce(sum(CASE g.tipo WHEN 'estorno' THEN -g.valor ELSE g.valor END), 0) AS total_pago,
       p.valor_face
         - coalesce(sum(CASE g.tipo WHEN 'estorno' THEN -g.valor ELSE g.valor END), 0) AS saldo
FROM precatorio p
LEFT JOIN pagamento g ON g.precatorio_id = p.id
GROUP BY p.id;

COMMIT;
