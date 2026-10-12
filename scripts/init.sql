-- ============================================
-- Blockchain Intelligence Platform Schema
-- ============================================

-- ADDRESSES TABLE: Every unique wallet/contract
CREATE TABLE IF NOT EXISTS addresses (
    id BIGSERIAL PRIMARY KEY,
    address VARCHAR(42) UNIQUE NOT NULL,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    label VARCHAR(100),
    is_blacklisted BOOLEAN DEFAULT FALSE,
    risk_score SMALLINT DEFAULT 0 CHECK (risk_score >= 0 AND risk_score <= 100),
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_addresses_address ON addresses(address);
CREATE INDEX IF NOT EXISTS idx_addresses_blacklisted ON addresses(is_blacklisted);

-- TRANSACTIONS TABLE: Every blockchain transfer
CREATE TABLE IF NOT EXISTS transactions (
    id BIGSERIAL PRIMARY KEY,
    hash VARCHAR(66) UNIQUE NOT NULL,
    from_address_id BIGINT NOT NULL REFERENCES addresses(id),
    to_address_id BIGINT REFERENCES addresses(id),
    value NUMERIC(78, 0) NOT NULL DEFAULT 0,
    gas_price NUMERIC(78, 0),
    gas_used NUMERIC(78, 0),
    block_number BIGINT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    risk_score SMALLINT DEFAULT 0 CHECK (risk_score >= 0 AND risk_score <= 100),
    risk_factors JSONB DEFAULT '[]'::jsonb,
    ai_explanation TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tx_hash ON transactions(hash);
CREATE INDEX IF NOT EXISTS idx_tx_from ON transactions(from_address_id);
CREATE INDEX IF NOT EXISTS idx_tx_to ON transactions(to_address_id);
CREATE INDEX IF NOT EXISTS idx_tx_block ON transactions(block_number);
CREATE INDEX IF NOT EXISTS idx_tx_timestamp ON transactions(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_tx_risk ON transactions(risk_score DESC);

-- ALERTS TABLE: High-risk notifications
CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,
    transaction_id BIGINT REFERENCES transactions(id),
    address_id BIGINT REFERENCES addresses(id),
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    message TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    acknowledged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_acknowledged ON alerts(acknowledged, created_at DESC);

-- BLACKLIST TABLE: Known bad actors
CREATE TABLE IF NOT EXISTS blacklist (
    id BIGSERIAL PRIMARY KEY,
    address VARCHAR(42) UNIQUE NOT NULL,
    reason TEXT,
    source VARCHAR(100),
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_blacklist_address ON blacklist(address);

-- Insert one example to prove it works
-- Note: Do NOT seed the null address (0x0000...0000) into the blacklist.
-- It is used for legitimate contract creation and burns.
-- Real blacklist entries should be known scammers/sanctioned addresses only.
-- Source-attributed verified sanctions intelligence, separate from manual blacklist.
CREATE TABLE IF NOT EXISTS verified_address_intelligence (
    source TEXT NOT NULL,
    address VARCHAR(42) NOT NULL,
    entity_id TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (source, address)
);
CREATE INDEX IF NOT EXISTS idx_verified_intelligence_address ON verified_address_intelligence(address);
