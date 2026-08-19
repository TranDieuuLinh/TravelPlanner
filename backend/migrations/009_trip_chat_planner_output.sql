ALTER TABLE agent_trip_chats
    ADD COLUMN IF NOT EXISTS current_planner_output jsonb;
