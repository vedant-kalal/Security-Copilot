-- ============================================================================
-- SentinelAI sample data (SQL reference).
--
-- This file illustrates the expected shape of seeded data for manual
-- `psql` inspection. The canonical, idempotent way to seed a fresh
-- database is `python scripts/seed_db.py`, which also embeds playbooks
-- via Gemini when GEMINI_API_KEY is configured — prefer that script for
-- actually populating a database. This SQL is provided as a readable
-- reference / fallback for environments without Python available.
--
-- Demo login after running scripts/seed_db.py: demo@sentinelai.io / SentinelDemo123!
-- ============================================================================

-- Example playbook row (see backend/app/data/playbooks/playbooks.json for the full set of 8)
INSERT INTO playbooks (id, title, mitre_techniques, content, created_at)
VALUES (
    uuid_generate_v4(),
    'Phishing Link Response Playbook',
    ARRAY['T1566', 'T1566.002'],
    E'PHISHING LINK RESPONSE\n\n1. Do not enter any credentials or personal information on the flagged page.\n2. Close the browser tab immediately.\n3. Reset any credentials that were entered.\n4. Enable multi-factor authentication.\n5. Report the URL to your security team.',
    now()
)
ON CONFLICT DO NOTHING;

-- Example user (password hash below corresponds to bcrypt('SentinelDemo123!'))
-- Prefer `python scripts/seed_db.py`, which hashes correctly at insert time;
-- this row is illustrative only and should not be relied on for login.
-- INSERT INTO users (id, email, password_hash, created_at)
-- VALUES (uuid_generate_v4(), 'demo@sentinelai.io', '<bcrypt-hash>', now());
