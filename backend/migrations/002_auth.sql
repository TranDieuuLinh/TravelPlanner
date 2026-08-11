BEGIN;

-- The legacy database already contains auth_users/auth_sessions with a
-- different contract. Keep this runtime schema isolated from those tables.
CREATE TABLE IF NOT EXISTS auth_runtime_users (
    id bigserial PRIMARY KEY,
    email text NOT NULL UNIQUE,
    full_name text NOT NULL,
    password_hash text NOT NULL,
    password_salt text NOT NULL,
    role text NOT NULL DEFAULT 'traveler'
        CHECK (role IN ('traveler', 'host', 'creator', 'admin')),
    status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'inactive', 'banned')),
    avatar_url text,
    bio text,
    travel_preferences jsonb NOT NULL DEFAULT '[]'::jsonb,
    creator_status text NOT NULL DEFAULT 'none'
        CHECK (creator_status IN ('none', 'pending', 'verified', 'rejected')),
    creator_portfolio_urls jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS auth_runtime_sessions (
    token_hash char(64) PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES auth_runtime_users(id) ON DELETE CASCADE,
    csrf_token_hash char(64) NOT NULL,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_used_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS auth_runtime_sessions_user_id_idx ON auth_runtime_sessions(user_id);
CREATE INDEX IF NOT EXISTS auth_runtime_sessions_expires_at_idx ON auth_runtime_sessions(expires_at);

COMMIT;
