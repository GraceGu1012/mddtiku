-- Historical papers remain review drafts, separate from the published items library.
CREATE TABLE IF NOT EXISTS exam_papers (
 id text PRIMARY KEY,
 year integer NOT NULL,
 title text NOT NULL,
 type text NOT NULL DEFAULT 'past_exam' CHECK (type='past_exam'),
 review_status text NOT NULL DEFAULT 'pending_review' CHECK (review_status IN ('pending_review','approved')),
 category_id text,
 -- cloud copy: no categories table in the learner-only cloud schema
 content_sha256 text NOT NULL,
 payload jsonb NOT NULL,
 source_files jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS exam_questions (
 paper_id text NOT NULL REFERENCES exam_papers(id) ON DELETE CASCADE,
 number integer NOT NULL CHECK (number>0),
 kind text NOT NULL CHECK (kind IN ('single_choice','multiple_choice')),
 answer_status text NOT NULL CHECK (answer_status IN ('unresolved','candidate')),
 review_status text NOT NULL DEFAULT 'pending_review' CHECK (review_status IN ('pending_review','approved')),
 payload jsonb NOT NULL,
 PRIMARY KEY (paper_id,number)
);

-- Enrichment changes retain a complete previous paper for review and recovery.
CREATE TABLE IF NOT EXISTS exam_paper_revisions (
 id bigserial PRIMARY KEY,
 paper_id text NOT NULL REFERENCES exam_papers(id),
 before_sha256 text NOT NULL,
 after_sha256 text NOT NULL,
 before_snapshot jsonb NOT NULL,
 actor text NOT NULL CHECK (length(btrim(actor))>0),
 reason text NOT NULL CHECK (length(btrim(reason))>0),
 job_id text,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS exam_paper_revisions_paper ON exam_paper_revisions(paper_id,id);

-- Approval is separate from immutable imported content and its SHA256.
CREATE TABLE IF NOT EXISTS exam_review_events (
 id bigserial PRIMARY KEY,
 paper_id text NOT NULL REFERENCES exam_papers(id),
 content_sha256 text NOT NULL,
 before_snapshot jsonb NOT NULL,
 actor text NOT NULL CHECK(length(btrim(actor))>0),
 reason text NOT NULL CHECK(length(btrim(reason))>0),
 question_count integer NOT NULL,
 unresolved_count integer NOT NULL,
 action text NOT NULL DEFAULT 'approve' CHECK(action='approve'),
 created_at timestamptz NOT NULL DEFAULT now()
);

-- Full-paper practice is separate from generated course questions and XP.
CREATE TABLE IF NOT EXISTS exam_paper_sessions (
 id text PRIMARY KEY,
 learner_id text NOT NULL REFERENCES learners(id),
 paper_id text NOT NULL REFERENCES exam_papers(id),
 content_sha256 text NOT NULL,
 title text NOT NULL,
 snapshot jsonb NOT NULL,
 answers jsonb NOT NULL DEFAULT '{}',
 revision integer NOT NULL DEFAULT 0,
 result jsonb,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 submitted_at timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS exam_paper_sessions_open ON exam_paper_sessions(learner_id,paper_id,content_sha256) WHERE submitted_at IS NULL;
CREATE INDEX IF NOT EXISTS exam_paper_sessions_learner ON exam_paper_sessions(learner_id,created_at DESC);
