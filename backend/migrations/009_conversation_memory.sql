-- Migration 009: Conversation Memory persistence tables & legacy schema upgrade
-- Idempotent script supporting rollout on new and existing databases with legacy data.
BEGIN;

-- 1. Create agent_conversation_memory if not exists
CREATE TABLE IF NOT EXISTS agent_conversation_memory (
    chat_id text PRIMARY KEY,
    user_id integer NOT NULL,
    destination text,
    duration_days integer CHECK (duration_days IS NULL OR (duration_days >= 1 AND duration_days <= 90)),
    travelers integer CHECK (travelers IS NULL OR (travelers >= 1 AND travelers <= 50)),
    budget jsonb NOT NULL DEFAULT 'null'::jsonb,
    preferences jsonb NOT NULL DEFAULT '[]'::jsonb,
    avoids jsonb NOT NULL DEFAULT '[]'::jsonb,
    mentioned_places jsonb NOT NULL DEFAULT '[]'::jsonb,
    selected_places jsonb NOT NULL DEFAULT '[]'::jsonb,
    active_references jsonb NOT NULL DEFAULT '[]'::jsonb,
    current_plan_ref text,
    pending_goal text,
    last_route varchar(64),
    summary text,
    version integer NOT NULL DEFAULT 0 CHECK (version >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_agent_conv_memory_chat_user UNIQUE (chat_id, user_id)
);

-- Upgrade columns on existing agent_conversation_memory
ALTER TABLE agent_conversation_memory
    ADD COLUMN IF NOT EXISTS travelers integer CHECK (travelers IS NULL OR (travelers >= 1 AND travelers <= 50));

ALTER TABLE agent_conversation_memory
    ADD COLUMN IF NOT EXISTS active_references jsonb NOT NULL DEFAULT '[]'::jsonb;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'uq_agent_conv_memory_chat_user'
    ) THEN
        ALTER TABLE agent_conversation_memory
            ADD CONSTRAINT uq_agent_conv_memory_chat_user UNIQUE (chat_id, user_id);
    END IF;
END $$;

-- 2. Create agent_conversation_memory_facts if not exists
CREATE TABLE IF NOT EXISTS agent_conversation_memory_facts (
    fact_id text PRIMARY KEY,
    chat_id text NOT NULL,
    user_id integer NOT NULL,
    fact_type varchar(64) NOT NULL,
    key varchar(120) NOT NULL,
    value jsonb NOT NULL,
    normalized_value text NOT NULL DEFAULT '',
    value_type varchar(32) NOT NULL DEFAULT 'string',
    scope varchar(16) NOT NULL DEFAULT 'chat' CHECK (scope IN ('chat', 'user')),
    status varchar(16) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'superseded', 'expired', 'rejected')),
    confirmed_by_user boolean NOT NULL DEFAULT false,
    confidence double precision NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    source_turn integer NOT NULL DEFAULT 0 CHECK (source_turn >= 0),
    source_excerpt varchar(200) NOT NULL,
    source_message_id text,
    source_url varchar(500),
    extracted_by varchar(80) NOT NULL,
    observed_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Upgrade facts table columns if upgrading existing table
ALTER TABLE agent_conversation_memory_facts
    ADD COLUMN IF NOT EXISTS normalized_value text NOT NULL DEFAULT '';

ALTER TABLE agent_conversation_memory_facts
    ADD COLUMN IF NOT EXISTS source_url varchar(500);

-- Canonicalize every legacy value, even when normalized_value is already populated.
-- Runtime and migration must use the same representation before deduplication.
UPDATE agent_conversation_memory_facts
SET normalized_value = lower(
    regexp_replace(
        trim(
            CASE
                WHEN jsonb_typeof(value) = 'string' THEN value #>> '{}'
                ELSE value::text
            END
        ),
        '\s+', ' ', 'g'
    )
);

-- Do not silently reassign ownership or create synthetic chats during rollout.
-- A mismatch/orphan is a data-integrity incident and must abort this transaction.
DO $$
DECLARE
    mismatch_count integer;
    orphan_fact_count integer;
    orphan_memory_count integer;
BEGIN
    SELECT count(*) INTO mismatch_count
    FROM agent_conversation_memory_facts f
    JOIN agent_conversation_memory m ON m.chat_id = f.chat_id
    WHERE f.user_id <> m.user_id;

    SELECT count(*) INTO orphan_fact_count
    FROM agent_conversation_memory_facts f
    WHERE NOT EXISTS (
        SELECT 1 FROM agent_conversation_memory m WHERE m.chat_id = f.chat_id
    );

    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'agent_trip_chats') THEN
        SELECT count(*) INTO orphan_memory_count
        FROM agent_conversation_memory m
        WHERE NOT EXISTS (
            SELECT 1 FROM agent_trip_chats c WHERE c.id = m.chat_id
        );
    ELSE
        orphan_memory_count := 0;
    END IF;

    IF mismatch_count > 0 OR orphan_fact_count > 0 OR orphan_memory_count > 0 THEN
        RAISE EXCEPTION
            'conversation memory migration aborted: ownership/orphan violations (mismatched facts=%, orphan facts=%, orphan memories=%)',
            mismatch_count, orphan_fact_count, orphan_memory_count
            USING ERRCODE = '23514';
    END IF;
END $$;

-- Ensure composite FK on (chat_id, user_id) exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_conv_memory_facts_parent'
    ) THEN
        ALTER TABLE agent_conversation_memory_facts
            ADD CONSTRAINT fk_conv_memory_facts_parent
            FOREIGN KEY (chat_id, user_id)
            REFERENCES agent_conversation_memory (chat_id, user_id) ON DELETE CASCADE;
    END IF;
END $$;

-- Deduplicate legacy active facts before creating unique index:
-- Keep highest priority fact active (confirmed_by_user DESC, confidence DESC, created_at DESC), mark others superseded
WITH ranked_facts AS (
    SELECT
        fact_id,
        ROW_NUMBER() OVER (
            PARTITION BY chat_id, key, normalized_value
            ORDER BY confirmed_by_user DESC, confidence DESC, created_at DESC
        ) AS rnk
    FROM agent_conversation_memory_facts
    WHERE status = 'active'
)
UPDATE agent_conversation_memory_facts
SET status = 'superseded', updated_at = now()
WHERE fact_id IN (
    SELECT fact_id FROM ranked_facts WHERE rnk > 1
);

-- Drop legacy unique index if present from older Phase 01 migration
DROP INDEX IF EXISTS idx_agent_conv_memory_facts_active_key;

-- Create unique index on active facts by chat_id, key, normalized_value
CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_conv_memory_facts_active_norm
    ON agent_conversation_memory_facts (chat_id, key, normalized_value) WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_agent_conv_memory_user_updated
    ON agent_conversation_memory (user_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_conv_memory_facts_chat_status
    ON agent_conversation_memory_facts (chat_id, status);

CREATE INDEX IF NOT EXISTS idx_agent_conv_memory_facts_user_scope_status
    ON agent_conversation_memory_facts (user_id, scope, status);

-- Safely link to agent_trip_chats if table exists
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables WHERE table_name = 'agent_trip_chats'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints WHERE constraint_name = 'fk_agent_conv_memory_trip_chat'
    ) THEN
        ALTER TABLE agent_conversation_memory
            ADD CONSTRAINT fk_agent_conv_memory_trip_chat
            FOREIGN KEY (chat_id) REFERENCES agent_trip_chats(id) ON DELETE CASCADE;
    END IF;
END $$;

COMMIT;
