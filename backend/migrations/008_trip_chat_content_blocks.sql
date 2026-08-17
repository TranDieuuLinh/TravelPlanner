-- Store Information Finder structured output beside legacy assistant text.
BEGIN;

ALTER TABLE agent_trip_chat_messages
  ADD COLUMN IF NOT EXISTS content_blocks jsonb NOT NULL DEFAULT '[]'::jsonb;

COMMIT;
