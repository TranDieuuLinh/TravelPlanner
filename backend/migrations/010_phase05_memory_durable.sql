-- Migration 010: Phase 05 durable-memory rollout safeguards.
-- LangGraph checkpoint tables are created idempotently by AsyncPostgresSaver.setup().
BEGIN;

CREATE INDEX IF NOT EXISTS idx_agent_conv_memory_user_scope_active
    ON agent_conversation_memory_facts (user_id, scope, status, created_at DESC);

-- Retain audit history by default; callers may explicitly expire old rejected
-- or superseded facts after their retention policy has been approved.
CREATE OR REPLACE FUNCTION expire_old_conversation_memory_facts(
    retention_interval interval DEFAULT interval '365 days'
)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE changed integer;
BEGIN
    UPDATE agent_conversation_memory_facts
    SET status = 'expired', updated_at = now()
    WHERE status IN ('superseded', 'rejected')
      AND updated_at < now() - retention_interval;
    GET DIAGNOSTICS changed = ROW_COUNT;
    RETURN changed;
END;
$$;

COMMIT;
