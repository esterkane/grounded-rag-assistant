-- Phase 5: review UI and feedback capture.
--
-- query_log records every /ask call; feedback captures human review of a logged
-- answer. `flagged` isolates insufficient / low-confidence answers for the review
-- queue. `payload` stores the full structured GroundedAnswer (claims, sources,
-- dropped citations) so the detail page can show retrieved chunks and citations
-- without re-running retrieval.

CREATE TABLE IF NOT EXISTS query_log (
    id            BIGSERIAL PRIMARY KEY,
    query         TEXT        NOT NULL,
    answer        TEXT        NOT NULL DEFAULT '',
    answered      BOOLEAN     NOT NULL DEFAULT FALSE,
    flagged       BOOLEAN     NOT NULL DEFAULT FALSE,
    latency_ms    INTEGER,
    provider      TEXT        NOT NULL DEFAULT '',
    retrieval_mode TEXT       NOT NULL DEFAULT '',
    payload       JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_query_log_flagged_created
    ON query_log (flagged, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_query_log_created
    ON query_log (created_at DESC);

CREATE TABLE IF NOT EXISTS feedback (
    id              BIGSERIAL PRIMARY KEY,
    query_log_id    BIGINT      NOT NULL REFERENCES query_log (id) ON DELETE CASCADE,
    rating          TEXT        NOT NULL,
    correction_text TEXT,
    reviewer        TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_feedback_query_log_id
    ON feedback (query_log_id);
