-- ChainScope intelligence v2: sparse historical evidence, source-attributed entities,
-- and independently labelled detection evaluation. Safe additive migration only.

CREATE TABLE IF NOT EXISTS wallet_transfer_evidence (
    chain_id BIGINT NOT NULL DEFAULT 1,
    wallet_address VARCHAR(42) NOT NULL,
    evidence_key TEXT NOT NULL,
    provider TEXT NOT NULL,
    provider_unique_id TEXT,
    tx_hash VARCHAR(66),
    category TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('incoming', 'outgoing')),
    from_address VARCHAR(42),
    to_address VARCHAR(42),
    asset TEXT,
    value_text TEXT,
    token_id TEXT,
    contract_address VARCHAR(42),
    block_number BIGINT,
    block_timestamp TIMESTAMPTZ,
    raw_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_url TEXT,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (chain_id, wallet_address, evidence_key)
);
CREATE INDEX IF NOT EXISTS idx_wallet_transfer_wallet_block
    ON wallet_transfer_evidence(chain_id, wallet_address, block_number DESC);
CREATE INDEX IF NOT EXISTS idx_wallet_transfer_hash
    ON wallet_transfer_evidence(tx_hash) WHERE tx_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_wallet_transfer_counterparties
    ON wallet_transfer_evidence(from_address, to_address);

CREATE TABLE IF NOT EXISTS wallet_history_sync (
    chain_id BIGINT NOT NULL DEFAULT 1,
    wallet_address VARCHAR(42) NOT NULL,
    provider TEXT NOT NULL,
    categories JSONB NOT NULL DEFAULT '[]'::jsonb,
    outgoing_page_key TEXT,
    incoming_page_key TEXT,
    outgoing_complete BOOLEAN NOT NULL DEFAULT FALSE,
    incoming_complete BOOLEAN NOT NULL DEFAULT FALSE,
    newest_block BIGINT,
    oldest_block BIGINT,
    records_cached BIGINT NOT NULL DEFAULT 0,
    last_error TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (chain_id, wallet_address, provider)
);

CREATE TABLE IF NOT EXISTS entity_attributions (
    chain_id BIGINT NOT NULL DEFAULT 1,
    address VARCHAR(42) NOT NULL,
    source TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    confidence NUMERIC(5,4) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    attribution_scope TEXT NOT NULL DEFAULT 'address',
    source_url TEXT,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    verified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    PRIMARY KEY (chain_id, address, source, entity_id)
);
CREATE INDEX IF NOT EXISTS idx_entity_attributions_address
    ON entity_attributions(chain_id, address);
CREATE INDEX IF NOT EXISTS idx_entity_attributions_name
    ON entity_attributions(entity_name);
CREATE INDEX IF NOT EXISTS idx_entity_attributions_type
    ON entity_attributions(entity_type);

CREATE TABLE IF NOT EXISTS detection_labels (
    id BIGSERIAL PRIMARY KEY,
    tx_hash VARCHAR(66) NOT NULL,
    label SMALLINT NOT NULL CHECK (label IN (0, 1)),
    label_source TEXT NOT NULL,
    label_reference TEXT NOT NULL,
    notes TEXT,
    labelled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tx_hash, label_source, label_reference)
);

CREATE TABLE IF NOT EXISTS detection_evaluations (
    id BIGSERIAL PRIMARY KEY,
    evaluator_version TEXT NOT NULL,
    threshold SMALLINT NOT NULL,
    sample_size BIGINT NOT NULL,
    metrics JSONB NOT NULL,
    label_sources JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_detection_evaluations_created
    ON detection_evaluations(created_at DESC);
