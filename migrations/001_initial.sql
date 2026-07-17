CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY,
    username TEXT,
    full_name TEXT NOT NULL,
    referred_by BIGINT REFERENCES users(id),
    is_robot BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS balances (
    user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    balance BIGINT NOT NULL DEFAULT 0 CHECK (balance >= 0),
    coins BIGINT NOT NULL DEFAULT 0 CHECK (coins >= 0),
    active_skin TEXT NOT NULL DEFAULT 'default',
    rating_points INTEGER NOT NULL DEFAULT 1000 CHECK (rating_points >= 0)
);

ALTER TABLE balances ADD COLUMN IF NOT EXISTS coins BIGINT NOT NULL DEFAULT 0;
ALTER TABLE balances ADD COLUMN IF NOT EXISTS active_skin TEXT NOT NULL DEFAULT 'default';
ALTER TABLE balances ADD COLUMN IF NOT EXISTS rating_points INTEGER NOT NULL DEFAULT 1000;

CREATE TABLE IF NOT EXISTS inventory (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    skin_id TEXT NOT NULL,
    bought_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    UNIQUE(user_id, skin_id)
);

ALTER TABLE inventory ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'created_at'
          AND data_type = 'timestamp without time zone'
    ) THEN
        ALTER TABLE users ALTER COLUMN created_at TYPE TIMESTAMPTZ
        USING created_at AT TIME ZONE 'UTC';
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'inventory' AND column_name = 'bought_at'
          AND data_type = 'timestamp without time zone'
    ) THEN
        ALTER TABLE inventory ALTER COLUMN bought_at TYPE TIMESTAMPTZ
        USING bought_at AT TIME ZONE 'UTC';
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'inventory' AND column_name = 'expires_at'
          AND data_type = 'timestamp without time zone'
    ) THEN
        ALTER TABLE inventory ALTER COLUMN expires_at TYPE TIMESTAMPTZ
        USING expires_at AT TIME ZONE 'UTC';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS referrals (
    id BIGSERIAL PRIMARY KEY,
    inviter_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    referred_id BIGINT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'rewarded')),
    reward BIGINT NOT NULL DEFAULT 50000,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    rewarded_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS wallet_transactions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    currency TEXT NOT NULL CHECK (currency IN ('cash', 'coin')),
    amount BIGINT NOT NULL,
    transaction_type TEXT NOT NULL,
    reference_id TEXT,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS game_results (
    id BIGSERIAL PRIMARY KEY,
    game_id TEXT NOT NULL,
    user_id BIGINT NOT NULL REFERENCES users(id),
    mode TEXT NOT NULL DEFAULT 'classic',
    rank INTEGER NOT NULL,
    is_draw BOOLEAN NOT NULL DEFAULT FALSE,
    draw_type TEXT,
    reward BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE game_results ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'classic';
ALTER TABLE game_results ADD COLUMN IF NOT EXISTS draw_type TEXT;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'game_results' AND column_name = 'created_at'
          AND data_type = 'timestamp without time zone'
    ) THEN
        ALTER TABLE game_results ALTER COLUMN created_at TYPE TIMESTAMPTZ
        USING created_at AT TIME ZONE 'UTC';
    END IF;
END $$;

DELETE FROM game_results older
USING game_results newer
WHERE older.id < newer.id
  AND older.game_id = newer.game_id
  AND older.user_id = newer.user_id;

CREATE UNIQUE INDEX IF NOT EXISTS uq_game_results_game_user
ON game_results(game_id, user_id);

CREATE TABLE IF NOT EXISTS game_sessions (
    game_id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('waiting', 'active', 'finished', 'cancelled')),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_game_sessions_status ON game_sessions(status);
CREATE INDEX IF NOT EXISTS idx_users_referred_by ON users(referred_by);
CREATE INDEX IF NOT EXISTS idx_game_results_user ON game_results(user_id);
