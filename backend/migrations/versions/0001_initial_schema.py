"""initial schema

Creates every table defined in the SentinelAI architecture document
(section 17 "Database Design"): users, devices, sessions, events,
incidents, evidence, ai_responses, threat_cache — plus the `playbooks`
table that backs the RAG pipeline, and the `pgvector` extension it
depends on.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-01-01 00:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 768


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")

    event_type_enum = postgresql.ENUM(
        "page_navigation",
        "url_visit",
        "file_download",
        "form_submission",
        "login_attempt",
        "network_flow",
        "network_flow_replay",
        "network_flow_upload",
        name="event_type_enum",
    )
    incident_severity_enum = postgresql.ENUM("low", "medium", "high", "critical", name="incident_severity_enum")
    incident_status_enum = postgresql.ENUM(
        "open", "investigating", "contained", "resolved", "dismissed", name="incident_status_enum"
    )
    threat_intel_source_enum = postgresql.ENUM("virustotal", "abuseipdb", "phishtank", name="threat_intel_source_enum")

    bind = op.get_bind()
    event_type_enum.create(bind, checkfirst=True)
    incident_severity_enum.create(bind, checkfirst=True)
    incident_status_enum.create(bind, checkfirst=True)
    threat_intel_source_enum.create(bind, checkfirst=True)

    # --- users -----------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # --- devices -----------------------------------------------------------
    op.create_table(
        "devices",
        sa.Column("device_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("browser", sa.String(100), nullable=False),
        sa.Column("os", sa.String(100), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_devices_user_id", "devices", ["user_id"])

    # --- sessions -----------------------------------------------------------
    op.create_table(
        "sessions",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "device_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("devices.device_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("login_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("logout_time", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_sessions_device_id", "sessions", ["device_id"])

    # --- events -----------------------------------------------------------
    op.create_table(
        "events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "device_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("devices.device_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("event_type", event_type_enum, nullable=False),
        sa.Column("payload_json", postgresql.JSONB, nullable=False, server_default="{}"),
    )
    op.create_index("ix_events_device_id", "events", ["device_id"])
    op.create_index("ix_events_timestamp", "events", ["timestamp"])
    op.create_index("ix_events_event_type", "events", ["event_type"])

    # --- incidents -----------------------------------------------------------
    op.create_table(
        "incidents",
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("severity", incident_severity_enum, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("mitre", postgresql.ARRAY(sa.String(20)), nullable=False, server_default="{}"),
        sa.Column("status", incident_status_enum, nullable=False, server_default="open"),
        sa.Column("summary", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_incidents_user_id", "incidents", ["user_id"])
    op.create_index("ix_incidents_severity", "incidents", ["severity"])
    op.create_index("ix_incidents_status", "incidents", ["status"])
    op.create_index("ix_incidents_created_at", "incidents", ["created_at"])

    # --- evidence -----------------------------------------------------------
    op.create_table(
        "evidence",
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.incident_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.event_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_evidence_incident_id", "evidence", ["incident_id"])
    op.create_index("ix_evidence_event_id", "evidence", ["event_id"])

    # --- ai_responses -----------------------------------------------------------
    op.create_table(
        "ai_responses",
        sa.Column("response_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.incident_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("recommendation", sa.Text, nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ai_responses_incident_id", "ai_responses", ["incident_id"])

    # --- threat_cache -----------------------------------------------------------
    op.create_table(
        "threat_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("indicator", sa.String(512), nullable=False),
        sa.Column("source", threat_intel_source_enum, nullable=False),
        sa.Column("reputation", sa.Float, nullable=False, server_default="0"),
        sa.Column("raw_response", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "last_checked",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_threat_cache_indicator", "threat_cache", ["indicator"])
    op.create_unique_constraint(
        "uq_threat_cache_indicator_source", "threat_cache", ["indicator", "source"]
    )

    # --- playbooks (RAG support table) --------------------------------------
    op.create_table(
        "playbooks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("mitre_techniques", postgresql.ARRAY(sa.String(20)), nullable=False, server_default="{}"),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute(
        "CREATE INDEX ix_playbooks_embedding ON playbooks "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    op.drop_table("playbooks")
    op.drop_table("threat_cache")
    op.drop_table("ai_responses")
    op.drop_table("evidence")
    op.drop_table("incidents")
    op.drop_table("events")
    op.drop_table("sessions")
    op.drop_table("devices")
    op.drop_table("users")

    bind = op.get_bind()
    postgresql.ENUM(name="threat_intel_source_enum").drop(bind, checkfirst=True)
    postgresql.ENUM(name="incident_status_enum").drop(bind, checkfirst=True)
    postgresql.ENUM(name="incident_severity_enum").drop(bind, checkfirst=True)
    postgresql.ENUM(name="event_type_enum").drop(bind, checkfirst=True)
