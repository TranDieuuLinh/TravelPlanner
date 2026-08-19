-- Runtime/legacy tables retained by the current TravelPlanner database.
-- This migration is additive and intentionally does not import application data.
BEGIN;

-- Complete columns/uniqueness that were present in the runtime export but were
-- missing from the original Knowledge Graph migration.
ALTER TABLE knowledge_aliases
    ADD COLUMN IF NOT EXISTS alias_type varchar NOT NULL DEFAULT 'alternate_name',
    ADD COLUMN IF NOT EXISTS source text,
    ADD COLUMN IF NOT EXISTS provider varchar,
    ADD COLUMN IF NOT EXISTS status varchar NOT NULL DEFAULT 'imported',
    ADD COLUMN IF NOT EXISTS confidence double precision,
    ADD COLUMN IF NOT EXISTS verified_at timestamptz;
ALTER TABLE knowledge_aliases ALTER COLUMN language SET DEFAULT 'en';
CREATE UNIQUE INDEX IF NOT EXISTS uq_knowledge_aliases_entity_alias
    ON knowledge_aliases(entity_id, alias);

ALTER TABLE knowledge_properties
    ADD COLUMN IF NOT EXISTS note text,
    ADD COLUMN IF NOT EXISTS fetch_at timestamptz;
CREATE UNIQUE INDEX IF NOT EXISTS uq_knowledge_properties_entity_key
    ON knowledge_properties(entity_id, key);
CREATE UNIQUE INDEX IF NOT EXISTS uq_knowledge_relationships_edge
    ON knowledge_relationships(from_entity_id, relationship_type, to_entity_id);

CREATE TABLE IF NOT EXISTS users (
    id serial PRIMARY KEY, email varchar NOT NULL, full_name varchar NOT NULL,
    role varchar NOT NULL DEFAULT 'traveler', avatar_url varchar,
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
    status varchar NOT NULL DEFAULT 'active', password_hash varchar, bio text,
    creator_status varchar NOT NULL DEFAULT 'none', creator_portfolio_urls json NOT NULL DEFAULT '[]'::json
);
CREATE UNIQUE INDEX IF NOT EXISTS users_email_key ON users(email);

CREATE TABLE IF NOT EXISTS auth_users (
    id bigserial PRIMARY KEY, email text NOT NULL UNIQUE, full_name text NOT NULL,
    password_hash text NOT NULL, password_salt text NOT NULL,
    role text NOT NULL DEFAULT 'traveler' CHECK (role IN ('traveler','host','creator','admin')),
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive','banned')),
    avatar_url text, bio text, travel_preferences jsonb NOT NULL DEFAULT '[]'::jsonb,
    creator_status text NOT NULL DEFAULT 'none' CHECK (creator_status IN ('none','pending','verified','rejected')),
    creator_portfolio_urls jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS auth_sessions (
    id serial PRIMARY KEY, user_id integer NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    jti varchar NOT NULL, refresh_token_hash varchar NOT NULL, expires_at timestamptz NOT NULL,
    revoked_at timestamptz, replaced_by_jti varchar, created_at timestamptz NOT NULL DEFAULT now(), last_used_at timestamptz
);

CREATE TABLE IF NOT EXISTS trip_chats (
    id varchar PRIMARY KEY, user_id integer NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title varchar NOT NULL, destination varchar, current_plan json, current_intake_id varchar,
    revision integer NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
    latest_explorer_timing json, latest_planner_timing json, conversation_phase varchar NOT NULL,
    conversation_context json NOT NULL, active_pending_turn_id varchar, current_trip_intent json,
    trip_intent_version integer NOT NULL DEFAULT 0, trip_intent_plan_status varchar NOT NULL DEFAULT 'synced'
);
CREATE TABLE IF NOT EXISTS trip_chat_messages (
    id varchar PRIMARY KEY, chat_id varchar NOT NULL REFERENCES trip_chats(id) ON DELETE CASCADE,
    role varchar NOT NULL, content text NOT NULL, sequence integer NOT NULL, attachment_names json NOT NULL,
    plan_revision integer, created_at timestamptz NOT NULL DEFAULT now(), turn_id varchar, message_kind varchar NOT NULL,
    content_blocks json NOT NULL, client_turn_id varchar, base_revision integer, status varchar, intent varchar,
    confidence double precision, requires_confirmation boolean NOT NULL DEFAULT false,
    proposed_operations json NOT NULL DEFAULT '[]'::json, assistant_blocks json NOT NULL DEFAULT '[]'::json,
    result_summary json NOT NULL DEFAULT '{}'::json, error_code varchar, error_message text,
    processing_started_at timestamptz, updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_trip_chat_message_sequence ON trip_chat_messages(chat_id, sequence);
CREATE UNIQUE INDEX IF NOT EXISTS uq_trip_chat_message_client_turn ON trip_chat_messages(chat_id, client_turn_id);
CREATE TABLE IF NOT EXISTS trip_revisions (
    id varchar PRIMARY KEY, chat_id varchar NOT NULL REFERENCES trip_chats(id) ON DELETE CASCADE,
    revision integer NOT NULL, plan_payload json NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
    intake_id varchar, trip_intent_payload json
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_trip_chat_revision ON trip_revisions(chat_id, revision);
CREATE TABLE IF NOT EXISTS planning_runs (
    id varchar PRIMARY KEY, user_id integer REFERENCES users(id) ON DELETE SET NULL, intake_id varchar,
    source varchar NOT NULL, mode varchar NOT NULL, destination varchar NOT NULL, status varchar NOT NULL,
    current_stage varchar, stage_count integer NOT NULL, error_code varchar, error_message text,
    summary_json json NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz
);
CREATE TABLE IF NOT EXISTS planning_run_stages (
    id varchar PRIMARY KEY, run_id varchar NOT NULL REFERENCES planning_runs(id) ON DELETE CASCADE,
    sequence integer NOT NULL, stage varchar NOT NULL, status varchar NOT NULL, duration_ms integer,
    input_json json NOT NULL, output_json json NOT NULL, error_json json NOT NULL, metadata_json json NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(run_id, sequence)
);

CREATE TABLE IF NOT EXISTS knowledge_entity_images (
    id bigserial PRIMARY KEY, image_title varchar, image_url text NOT NULL,
    entity_id text NOT NULL REFERENCES knowledge_entities(id) ON DELETE CASCADE,
    UNIQUE(entity_id, image_url)
);
CREATE TABLE IF NOT EXISTS knowledge_graph_imports (
    id varchar PRIMARY KEY, source_label varchar NOT NULL, source_url varchar, source_content text NOT NULL,
    status varchar NOT NULL DEFAULT 'extracting', schema_version varchar NOT NULL, ontology_version varchar NOT NULL,
    dataset_hash varchar NOT NULL, warnings json NOT NULL DEFAULT '[]'::json, node_count integer NOT NULL DEFAULT 0,
    edge_count integer NOT NULL DEFAULT 0, issue_count integer NOT NULL DEFAULT 0, created_by bigint REFERENCES users(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(), applied_at timestamptz, applied_dataset_hash varchar, error_message text,
    import_kind varchar NOT NULL DEFAULT 'knowledge_graph', batch_id varchar, source_document_id varchar,
    processing_status varchar NOT NULL DEFAULT 'succeeded', review_status varchar NOT NULL DEFAULT 'not_required',
    chat_id varchar REFERENCES trip_chats(id) ON DELETE CASCADE, destination varchar, destination_entity_id text REFERENCES knowledge_entities(id) ON DELETE SET NULL,
    candidate_reviews json NOT NULL DEFAULT '[]'::json, source_type varchar NOT NULL DEFAULT 'url', source_name varchar,
    image_mime_type varchar, image_data bytea, force_refresh boolean NOT NULL DEFAULT false, batch_position integer NOT NULL DEFAULT 0,
    attempt_count integer NOT NULL DEFAULT 0, result_revision integer, error_code varchar, explorer_timing json, planner_timing json,
    started_at timestamptz, finished_at timestamptz, updated_at timestamptz NOT NULL DEFAULT now(), processing_phase varchar NOT NULL DEFAULT 'queued'
);
CREATE TABLE IF NOT EXISTS knowledge_graph_import_nodes (
    id bigserial PRIMARY KEY, import_id varchar NOT NULL REFERENCES knowledge_graph_imports(id) ON DELETE CASCADE,
    temp_id varchar NOT NULL, entity_id varchar NOT NULL, type varchar NOT NULL, canonical_name varchar NOT NULL,
    aliases json NOT NULL DEFAULT '[]'::json, properties json NOT NULL DEFAULT '{}'::json, evidence json NOT NULL DEFAULT '[]'::json,
    confidence double precision NOT NULL DEFAULT 0.5, match_status varchar NOT NULL DEFAULT 'new', match_candidates json NOT NULL DEFAULT '[]'::json,
    selected_entity_id text REFERENCES knowledge_entities(id) ON DELETE SET NULL, decision varchar NOT NULL DEFAULT 'pending',
    validation_issues json NOT NULL DEFAULT '[]'::json, required_properties json NOT NULL DEFAULT '[]'::json, optional_properties json NOT NULL DEFAULT '[]'::json,
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), source_document_id varchar,
    candidate_key varchar, candidate_name varchar, search_region varchar, source_evidence json NOT NULL DEFAULT '{}'::json,
    provider varchar, provider_external_id varchar, provider_snapshot json NOT NULL DEFAULT '{}'::json, source_order integer,
    source_day integer, source_time_hint varchar, source_activity text, source_duration_minutes integer,
    preference_level varchar NOT NULL DEFAULT 'preferred', attributes json NOT NULL DEFAULT '[]'::json,
    reviewed_by bigint REFERENCES users(id) ON DELETE SET NULL, reviewed_at timestamptz, identity_status varchar NOT NULL DEFAULT 'unresolved', selection_method varchar,
    UNIQUE(import_id, temp_id)
);
CREATE TABLE IF NOT EXISTS knowledge_graph_import_edges (
    id bigserial PRIMARY KEY, import_id varchar NOT NULL REFERENCES knowledge_graph_imports(id) ON DELETE CASCADE,
    temp_id varchar NOT NULL, from_ref varchar NOT NULL, relationship_type varchar NOT NULL, to_ref varchar NOT NULL,
    recommendations json NOT NULL DEFAULT '[]'::json, source varchar NOT NULL, evidence json NOT NULL DEFAULT '[]'::json,
    confidence double precision NOT NULL DEFAULT 0.5, match_status varchar NOT NULL DEFAULT 'new', decision varchar NOT NULL DEFAULT 'pending',
    validation_issues json NOT NULL DEFAULT '[]'::json, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(import_id, temp_id)
);

CREATE TABLE IF NOT EXISTS traveler_profiles (
    user_id integer PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, version integer NOT NULL,
    observation_count integer NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS traveler_preference_signals (
    id varchar PRIMARY KEY, user_id integer NOT NULL REFERENCES traveler_profiles(user_id) ON DELETE CASCADE,
    dimension varchar NOT NULL, value varchar NOT NULL, label varchar NOT NULL, score double precision NOT NULL,
    confidence double precision NOT NULL, observations integer NOT NULL, position integer NOT NULL, scope varchar NOT NULL,
    destination varchar NOT NULL, origin varchar NOT NULL, status varchar NOT NULL, first_observed_at timestamptz NOT NULL DEFAULT now(),
    last_observed_at timestamptz NOT NULL DEFAULT now(), last_evidence_intake_id varchar,
    UNIQUE(user_id, dimension, value, scope, destination), CHECK(score BETWEEN -1 AND 1), CHECK(confidence BETWEEN 0 AND 1),
    CHECK(scope IN ('global','destination')), CHECK(origin IN ('explicit','inferred')), CHECK(status IN ('active','rejected'))
);
CREATE TABLE IF NOT EXISTS traveler_preference_signal_sources (
    signal_id varchar NOT NULL REFERENCES traveler_preference_signals(id) ON DELETE CASCADE,
    source_type varchar NOT NULL, PRIMARY KEY(signal_id, source_type)
);
CREATE TABLE IF NOT EXISTS preference_observation_jobs (
    id varchar PRIMARY KEY, message_id varchar NOT NULL UNIQUE REFERENCES trip_chat_messages(id) ON DELETE CASCADE,
    user_id integer NOT NULL REFERENCES users(id) ON DELETE CASCADE, status varchar NOT NULL,
    attempts integer NOT NULL, error_code varchar, error_message text, started_at timestamptz, completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK(status IN ('queued','running','completed','failed','skipped'))
);

CREATE TABLE IF NOT EXISTS audit_events (
    id varchar PRIMARY KEY, actor_id integer REFERENCES users(id) ON DELETE SET NULL, action varchar NOT NULL,
    resource_type varchar NOT NULL, resource_id varchar, request_id varchar, metadata json NOT NULL DEFAULT '{}'::json,
    created_at timestamptz NOT NULL DEFAULT now()
);
COMMIT;
