-- ============================================================================
-- SentinelAI database schema (PostgreSQL + pgvector)
--
-- This file is auto-generated from the SQLAlchemy models in
-- backend/app/models/ via `python scripts/export_schema.py`.
-- The authoritative, versioned source of truth is the Alembic migration
-- at backend/migrations/versions/0001_initial_schema.py — run
-- `alembic upgrade head` to actually provision a database. This file is
-- provided as a convenience reference and for manual `psql` setup.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";


-- Table: playbooks
CREATE TABLE playbooks (
	id UUID NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	mitre_techniques VARCHAR(20)[] NOT NULL, 
	content TEXT NOT NULL, 
	embedding VECTOR(768), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);


-- Table: threat_cache
CREATE TABLE threat_cache (
	id UUID NOT NULL, 
	indicator VARCHAR(512) NOT NULL, 
	source threat_intel_source_enum NOT NULL, 
	reputation FLOAT NOT NULL, 
	raw_response JSONB NOT NULL, 
	last_checked TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_threat_cache_indicator_source UNIQUE (indicator, source)
);

CREATE INDEX ix_threat_cache_indicator ON threat_cache (indicator);

-- Table: users
CREATE TABLE users (
	email VARCHAR(255) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (id)
);

CREATE UNIQUE INDEX ix_users_email ON users (email);

-- Table: devices
CREATE TABLE devices (
	device_id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	browser VARCHAR(100) NOT NULL, 
	os VARCHAR(100) NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (device_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_devices_user_id ON devices (user_id);

-- Table: incidents
CREATE TABLE incidents (
	incident_id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	severity incident_severity_enum NOT NULL, 
	confidence FLOAT NOT NULL, 
	mitre VARCHAR(20)[] NOT NULL, 
	status incident_status_enum NOT NULL, 
	summary TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (incident_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_incidents_user_id ON incidents (user_id);
CREATE INDEX ix_incidents_status ON incidents (status);
CREATE INDEX ix_incidents_severity ON incidents (severity);

-- Table: ai_responses
CREATE TABLE ai_responses (
	response_id UUID NOT NULL, 
	incident_id UUID NOT NULL, 
	summary TEXT NOT NULL, 
	recommendation TEXT NOT NULL, 
	generated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (response_id), 
	FOREIGN KEY(incident_id) REFERENCES incidents (incident_id) ON DELETE CASCADE
);

CREATE INDEX ix_ai_responses_incident_id ON ai_responses (incident_id);

-- Table: events
CREATE TABLE events (
	event_id UUID NOT NULL, 
	device_id UUID NOT NULL, 
	timestamp TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	event_type event_type_enum NOT NULL, 
	payload_json JSONB NOT NULL, 
	PRIMARY KEY (event_id), 
	FOREIGN KEY(device_id) REFERENCES devices (device_id) ON DELETE CASCADE
);

CREATE INDEX ix_events_device_id ON events (device_id);
CREATE INDEX ix_events_event_type ON events (event_type);
CREATE INDEX ix_events_timestamp ON events (timestamp);

-- Table: sessions
CREATE TABLE sessions (
	session_id UUID NOT NULL, 
	device_id UUID NOT NULL, 
	login_time TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	logout_time TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (session_id), 
	FOREIGN KEY(device_id) REFERENCES devices (device_id) ON DELETE CASCADE
);

CREATE INDEX ix_sessions_device_id ON sessions (device_id);

-- Table: evidence
CREATE TABLE evidence (
	evidence_id UUID NOT NULL, 
	incident_id UUID NOT NULL, 
	event_id UUID NOT NULL, 
	reason TEXT NOT NULL, 
	score FLOAT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (evidence_id), 
	FOREIGN KEY(incident_id) REFERENCES incidents (incident_id) ON DELETE CASCADE, 
	FOREIGN KEY(event_id) REFERENCES events (event_id) ON DELETE CASCADE
);

CREATE INDEX ix_evidence_event_id ON evidence (event_id);
CREATE INDEX ix_evidence_incident_id ON evidence (incident_id);
