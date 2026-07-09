-- loreconvo_0.8.1_downgrade.sql
-- Downgrade cleanup for LoreConvo keep_forever (v0.8.1) durability schema.
--
-- Run ONLY if downgrading FROM LoreConvo 0.8.1+ AND a tool issues
-- DELETE FROM sessions directly (bypassing the sessions_prunable view).
-- Running on a live 0.8.1+ system removes all keep_forever durability
-- enforcement. Back up sessions.db BEFORE running this script.
--
-- WARNING: After execution, sessions with keep_forever=1 lose all protection.
-- Any bare DELETE FROM sessions will delete them without error or warning.
-- Pre-0.8.1 LoreConvo code ignores the keep_forever column via
-- if-in-keys guards in _row_to_session, so the column itself is harmless.
--
-- IF EXISTS guards make this script idempotent (safe to run more than once)
-- and a no-op on systems where the schema was never installed.

DROP TRIGGER IF EXISTS sessions_prunable_delete;
DROP VIEW IF EXISTS sessions_prunable;
DROP TRIGGER IF EXISTS prevent_delete_pinned_sessions;

-- Note: the keep_forever column is NOT dropped. Pre-0.8.1 code ignores it.
-- To remove the column entirely (SQLite >= 3.35.0 only):
--   ALTER TABLE sessions DROP COLUMN keep_forever;
-- Do not run the DROP COLUMN line on SQLite < 3.35.0 -- it will fail.
