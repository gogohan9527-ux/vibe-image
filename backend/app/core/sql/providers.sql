CREATE TABLE IF NOT EXISTS provider_configs (
    provider_id TEXT PRIMARY KEY,
    base_url TEXT NOT NULL,
    default_model TEXT NULL,
    default_key_id TEXT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS provider_keys (
    id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL,
    label TEXT NOT NULL,
    encrypted_credentials BLOB NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_provider_keys_provider ON provider_keys(provider_id);

CREATE TABLE IF NOT EXISTS provider_models (
    provider_id TEXT NOT NULL,
    key_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    display_name TEXT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (provider_id, key_id, model_id)
);
CREATE INDEX IF NOT EXISTS idx_provider_models_key ON provider_models(provider_id, key_id);
