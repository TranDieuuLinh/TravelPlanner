-- Durable chat storage for the current /v1/trip-chats API.
-- These names are intentionally isolated from the legacy trip_chats schema.
BEGIN;

CREATE TABLE IF NOT EXISTS agent_trip_chats (
  id text PRIMARY KEY,
  user_id integer NOT NULL REFERENCES auth_runtime_users(id) ON DELETE CASCADE,
  thread_id text NOT NULL UNIQUE,
  title varchar(160) NOT NULL DEFAULT 'Chuyến đi mới',
  revision integer NOT NULL DEFAULT 0 CHECK (revision >= 0),
  current_itinerary jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_trip_chat_messages (
  id text PRIMARY KEY,
  chat_id text NOT NULL REFERENCES agent_trip_chats(id) ON DELETE CASCADE,
  sequence integer NOT NULL CHECK (sequence > 0),
  role varchar(16) NOT NULL CHECK (role IN ('user', 'assistant')),
  content text NOT NULL,
  route varchar(64),
  clarification_question text,
  warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
  sources jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (chat_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_agent_trip_chats_user_updated
  ON agent_trip_chats (user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_trip_chat_messages_chat_sequence
  ON agent_trip_chat_messages (chat_id, sequence);

COMMIT;
