-- Phase 6: per-/ask token and cost tracking on query_log.
--
-- estimated_cost_usd is a would-be cost from a static public price table (see
-- app/observability/cost.py) — logged even when the provider is free (gemini
-- free tier / local ollama) so cost can be reasoned about at scale.

ALTER TABLE query_log
    ADD COLUMN IF NOT EXISTS model             TEXT             NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS input_tokens      INTEGER          NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS output_tokens     INTEGER          NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS total_tokens      INTEGER          NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS estimated_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0;
