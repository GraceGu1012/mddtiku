CREATE TABLE IF NOT EXISTS materials (
 id text PRIMARY KEY, name text NOT NULL, type text NOT NULL, sha256 text NOT NULL UNIQUE,
 path text NOT NULL, size bigint NOT NULL, parse_state text NOT NULL DEFAULT 'uploaded',
 parsed jsonb, confirmed boolean NOT NULL DEFAULT false, error text,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS prompt_versions (
 id bigserial PRIMARY KEY, name text NOT NULL, content text NOT NULL, sha256 text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS settings (
 id integer PRIMARY KEY CHECK(id=1), version integer NOT NULL DEFAULT 1, value jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS batches (
 id text PRIMARY KEY, material_id text REFERENCES materials(id), metadata jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS items (
 id text PRIMARY KEY, batch_id text NOT NULL REFERENCES batches(id), kind text NOT NULL CHECK(kind IN ('card','single_choice','multiple_choice','true_false')),
 status text NOT NULL DEFAULT 'pending_review' CHECK(status IN ('pending_review','approved','rejected','deleted')),
 original jsonb NOT NULL, current jsonb NOT NULL, evidence jsonb NOT NULL,
 suspect boolean NOT NULL DEFAULT false, check_note text NOT NULL DEFAULT '',
 version integer NOT NULL DEFAULT 1, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS audit (
 id bigserial PRIMARY KEY, item_id text NOT NULL REFERENCES items(id), action text NOT NULL,
 actor text NOT NULL, reason text NOT NULL, before_data jsonb NOT NULL, after_data jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS jobs (
 id text PRIMARY KEY, material_id text NOT NULL REFERENCES materials(id), kind text NOT NULL,
 state text NOT NULL DEFAULT 'queued', config jsonb NOT NULL, result jsonb, error text,
 reserved_calls integer NOT NULL DEFAULT 0, created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz
);
CREATE TABLE IF NOT EXISTS calls (
 id bigserial PRIMARY KEY, job_id text REFERENCES jobs(id), purpose text NOT NULL,
 model text NOT NULL, usage jsonb, cost numeric, currency text, response_id text,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS items_status ON items(status,kind);
CREATE INDEX IF NOT EXISTS jobs_state ON jobs(state,created_at);
CREATE OR REPLACE VIEW approved_library AS SELECT * FROM items WHERE status='approved';
CREATE TABLE IF NOT EXISTS model_profiles (
 id text PRIMARY KEY, name text NOT NULL, provider text NOT NULL,
 base_url text NOT NULL, model text NOT NULL, json_mode boolean NOT NULL DEFAULT true,
 enabled boolean NOT NULL DEFAULT true, version integer NOT NULL DEFAULT 1,
 credential_id text, env_key boolean NOT NULL DEFAULT false,
 input_price numeric, output_price numeric, currency text NOT NULL DEFAULT 'CNY',
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS model_credentials (
 id text PRIMARY KEY, model_id text NOT NULL REFERENCES model_profiles(id),
 base_url text NOT NULL, ciphertext text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE calls ADD COLUMN IF NOT EXISTS model_profile_id text;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS model_version integer;

-- Learner records are independent of content review and generation.
CREATE TABLE IF NOT EXISTS learners (
 id text PRIMARY KEY, token_hash text NOT NULL UNIQUE, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS practice_sessions (
 id text PRIMARY KEY, learner_id text NOT NULL REFERENCES learners(id),
 questions jsonb NOT NULL, mode text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS practice_attempts (
 id bigserial PRIMARY KEY, session_id text NOT NULL REFERENCES practice_sessions(id),
 item_id text NOT NULL REFERENCES items(id), item_version integer NOT NULL,
 selected jsonb NOT NULL, correct boolean NOT NULL, snapshot jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(session_id,item_id)
);
CREATE INDEX IF NOT EXISTS practice_sessions_learner ON practice_sessions(learner_id,created_at);
CREATE INDEX IF NOT EXISTS practice_attempts_item ON practice_attempts(item_id,id DESC);
CREATE TABLE IF NOT EXISTS card_progress (
 learner_id text NOT NULL REFERENCES learners(id), item_id text NOT NULL REFERENCES items(id),
 item_version integer NOT NULL, rating text NOT NULL CHECK(rating IN ('again','unsure','remembered')),
 reviews integer NOT NULL DEFAULT 1, updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(learner_id,item_id)
);

-- Durable multi-agent checkpoints. Existing jobs/batches remain historical records.
CREATE TABLE IF NOT EXISTS agent_prompt_versions (
 id bigserial PRIMARY KEY, stage text NOT NULL CHECK(stage IN ('analysis','knowledge')),
 content text NOT NULL, sha256 text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS agent_steps (
 job_id text NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
 name text NOT NULL CHECK(name IN ('analysis','knowledge','generation')),
 state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','running','completed','failed','skipped')),
 result jsonb, error text, started_at timestamptz, finished_at timestamptz,
 PRIMARY KEY(job_id,name)
);
CREATE INDEX IF NOT EXISTS jobs_material_history ON jobs(material_id,created_at DESC,id);

-- Gamification: XP events, AI ask log, and a stable learner identity via WeChat openid.
ALTER TABLE learners ADD COLUMN IF NOT EXISTS openid text;
CREATE UNIQUE INDEX IF NOT EXISTS learners_openid ON learners(openid) WHERE openid IS NOT NULL;
ALTER TABLE learners ADD COLUMN IF NOT EXISTS nickname text NOT NULL DEFAULT '';
-- 账号资料：手机号（绑定后才能改用户名）与头像（压缩后的 data URL）。
ALTER TABLE learners ADD COLUMN IF NOT EXISTS phone text;
CREATE UNIQUE INDEX IF NOT EXISTS learners_phone ON learners(phone) WHERE phone IS NOT NULL;
ALTER TABLE learners ADD COLUMN IF NOT EXISTS avatar text;
CREATE TABLE IF NOT EXISTS xp_events (
 id bigserial PRIMARY KEY, learner_id text NOT NULL REFERENCES learners(id),
 kind text NOT NULL CHECK(kind IN ('answer_correct','card_mastered','streak_bonus')),
 xp integer NOT NULL CHECK(xp>0 AND xp<=100), item_id text,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS xp_events_learner ON xp_events(learner_id,created_at DESC);
CREATE INDEX IF NOT EXISTS xp_events_created ON xp_events(created_at);
CREATE TABLE IF NOT EXISTS ask_logs (
 id bigserial PRIMARY KEY, learner_id text NOT NULL REFERENCES learners(id),
 question text NOT NULL, answer text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ask_logs_learner ON ask_logs(learner_id,created_at DESC);
