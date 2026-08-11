BEGIN;

CREATE TABLE IF NOT EXISTS knowledge_auto_attach_rules (
    rule_id text PRIMARY KEY,
    name text NOT NULL,
    style_group text NOT NULL,
    entity_types text[] NOT NULL DEFAULT '{}',
    keywords text[] NOT NULL DEFAULT '{}',
    exact_names text[] NOT NULL DEFAULT '{}',
    exclude_keywords text[] NOT NULL DEFAULT '{}',
    time_duration text NOT NULL DEFAULT 'PT60M',
    time_windows jsonb NOT NULL DEFAULT '[]'::jsonb,
    override_count integer NOT NULL DEFAULT 0 CHECK (override_count >= 0),
    status text NOT NULL DEFAULT 'pending',
    source text NOT NULL DEFAULT 'attach_auto.yml',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS knowledge_auto_attach_rules_group_idx
    ON knowledge_auto_attach_rules(style_group);
CREATE INDEX IF NOT EXISTS knowledge_auto_attach_rules_status_idx
    ON knowledge_auto_attach_rules(status);

CREATE TABLE IF NOT EXISTS knowledge_auto_attach_aliases (
    keyword text PRIMARY KEY,
    aliases text[] NOT NULL DEFAULT '{}',
    source text NOT NULL DEFAULT 'attach_auto.yml',
    updated_at timestamptz NOT NULL DEFAULT now()
);

COMMIT;
