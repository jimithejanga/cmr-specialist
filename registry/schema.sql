-- Mock CMR registry: canonical DDL (frozen schema, persons-only v1).
--
-- SQLite (pilot) and PostgreSQL (VM) compatible. SQLAlchemy ``models.py``
-- creates the same tables; this file is the human-readable contract and the
-- source for a future Postgres migration. Money is integer kobo, never float.
-- Authorship (who inserted a row, when) is NOT stored here - that belongs to
-- the change feed (next slice), which reads these tables, not the reverse.

CREATE TABLE IF NOT EXISTS profiles (
    profile_id   TEXT PRIMARY KEY,          -- 'prof-' + 3 digits
    full_name    TEXT,                       -- nullable: partial knowledge is honest
    phone        TEXT UNIQUE,                -- 11-digit MSISDN when known
    email        TEXT UNIQUE,
    nin          TEXT UNIQUE,                -- 11 digits; persons-only v1 (orgs use tin later)
    kind         TEXT NOT NULL DEFAULT 'person',  -- dormant column; no org logic yet
    is_synthetic BOOLEAN NOT NULL DEFAULT 1,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS vehicles (
    vehicle_id       TEXT PRIMARY KEY,      -- 'veh-' + 3 digits
    plate            TEXT UNIQUE NOT NULL,
    chassis          TEXT UNIQUE,            -- nullable for admin compat; real rows always set
    owner_profile_id TEXT NOT NULL REFERENCES profiles (profile_id),
    cert_state       TEXT NOT NULL DEFAULT 'none',  -- none|pending|issued|expired (denormalised)
    version          INTEGER NOT NULL DEFAULT 1,     -- optimistic lock for operator edits
    is_synthetic     BOOLEAN NOT NULL DEFAULT 1,
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_vehicles_owner ON vehicles (owner_profile_id);

CREATE TABLE IF NOT EXISTS transfers (
    transfer_ref      TEXT PRIMARY KEY,     -- 'TRF-' + 4 digits
    vehicle_id        TEXT NOT NULL REFERENCES vehicles (vehicle_id),
    seller_profile_id TEXT NOT NULL REFERENCES profiles (profile_id),
    buyer_profile_id  TEXT NOT NULL REFERENCES profiles (profile_id),
    doc_ref           TEXT,
    status            TEXT NOT NULL DEFAULT 'initiated',  -- initiated|completed|void
    approved_by       TEXT,
    is_synthetic      BOOLEAN NOT NULL DEFAULT 1,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    -- INVARIANT (enforced in repository transaction): seller must equal the
    -- vehicle's current owner at commit. A transfer that does not move
    -- ownership is refused, never stored.
);
CREATE INDEX IF NOT EXISTS ix_transfers_vehicle ON transfers (vehicle_id);

CREATE TABLE IF NOT EXISTS receipts (
    rrr            TEXT PRIMARY KEY,        -- exactly 12 digits, natural key
    status         TEXT NOT NULL DEFAULT 'unpaid',  -- paid|unpaid|void
    amount_kobo    INTEGER NOT NULL,         -- integer kobo; the API speaks naira
    linked_account TEXT,                     -- set-once (NULL = unlinked)
    linked_at      TIMESTAMP,
    paid_at        TIMESTAMP,
    is_synthetic   BOOLEAN NOT NULL DEFAULT 1
    -- INVARIANT (enforced in repository): linked_account, once set, changes
    -- only through void-and-relink. Receipts say payment happened, not
    -- payment for what (purpose tracking is a future table, not a column).
);

CREATE TABLE IF NOT EXISTS certificates (
    cert_no        TEXT PRIMARY KEY,
    vehicle_id     TEXT NOT NULL REFERENCES vehicles (vehicle_id),
    status         TEXT NOT NULL DEFAULT 'active',  -- active|expired|revoked
    request_age_h  INTEGER,
    issued_at      TIMESTAMP,
    expires_at     TIMESTAMP,
    is_synthetic   BOOLEAN NOT NULL DEFAULT 1
    -- INVARIANT: at most one active certificate per vehicle (partial index
    -- below). History is kept: renewal expires the old row, never deletes it.
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_cert_per_vehicle
    ON certificates (vehicle_id) WHERE status = 'active';
CREATE VIEW IF NOT EXISTS active_certificates AS
    SELECT * FROM certificates WHERE status = 'active';

CREATE TABLE IF NOT EXISTS tokens (
    token_id     TEXT PRIMARY KEY,          -- 'tok-' + 6 digits
    profile_id   TEXT NOT NULL REFERENCES profiles (profile_id),
    channel      TEXT NOT NULL,              -- sms|email
    template     TEXT NOT NULL DEFAULT 'generic',
    delivered_at TIMESTAMP,                  -- NULL = queued
    is_synthetic BOOLEAN NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS ix_tokens_profile ON tokens (profile_id);

-- Registry-internal machinery (NOT a domain table): deterministic reference
-- counters so TRF-/CORR-/tok- numbers behave exactly like the legacy dict
-- backend's len()+1 numbering across reseeds.
CREATE TABLE IF NOT EXISTS registry_counters (
    name     TEXT PRIMARY KEY,              -- 'TRF' | 'CORR' | 'TOK'
    next_val INTEGER NOT NULL DEFAULT 1
);

-- Change feed: append-only memory of what happened. Written in-transaction
-- by every repository mutation (a change without a feed row is impossible);
-- read newest-first by operators. No UPDATE/DELETE path, ever.
CREATE TABLE IF NOT EXISTS registry_changes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actor       TEXT NOT NULL,               -- agent:<formulation> | <username> | system:reset
    action      TEXT NOT NULL,               -- insert|transfer|link|renew|token|reseed|update
    table_name  TEXT NOT NULL,
    row_key     TEXT NOT NULL,
    before_json TEXT,                        -- NULL = row did not exist
    after_json  TEXT
);
CREATE INDEX IF NOT EXISTS ix_changes_table_row ON registry_changes (table_name, row_key);
CREATE INDEX IF NOT EXISTS ix_changes_actor ON registry_changes (actor);
