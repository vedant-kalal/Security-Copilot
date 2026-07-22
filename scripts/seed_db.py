#!/usr/bin/env python3
"""
Seed the SentinelAI database with:

  1. The RAG playbook library (`backend/app/data/playbooks/playbooks.json`),
     embedded with Gemini if `GEMINI_API_KEY` is configured (falls back to
     un-embedded rows, which the RAG service still retrieves via MITRE
     technique overlap — see `app/services/rag_service.py`).
  2. A demo user + device + a couple of sample incidents, so a fresh
     clone has something to look at immediately after setup.

Usage:
    python scripts/seed_db.py
    python scripts/seed_db.py --skip-demo-data   # playbooks only
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select, text  # noqa: E402

from app.core.database import Base, engine, session_scope  # noqa: E402
from app.core.logging import configure_logging, get_logger  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.device import Device  # noqa: E402
from app.models.event import Event, EventType  # noqa: E402
from app.models.evidence import Evidence  # noqa: E402
from app.models.incident import Incident, IncidentSeverity, IncidentStatus  # noqa: E402
from app.models.playbook import Playbook  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.llm_service import LLMService  # noqa: E402

configure_logging()
logger = get_logger("seed_db")

PLAYBOOKS_PATH = BACKEND_DIR / "app" / "data" / "playbooks" / "playbooks.json"
DEMO_EMAIL = "demo@sentinelai.io"
DEMO_PASSWORD = "SentinelDemo123!"


async def seed_playbooks() -> None:
    playbooks_data = json.loads(PLAYBOOKS_PATH.read_text())
    llm = LLMService()

    async with session_scope() as session:
        existing_titles = set(
            (await session.execute(select(Playbook.title))).scalars().all()
        )

        created = 0
        for entry in playbooks_data:
            if entry["title"] in existing_titles:
                continue

            embedding = await llm.embed_text(f"{entry['title']}\n{entry['content']}")
            playbook = Playbook(
                title=entry["title"],
                mitre_techniques=entry["mitre_techniques"],
                content=entry["content"],
                embedding=embedding,
            )
            session.add(playbook)
            created += 1

        logger.info(
            "Playbooks: %d created, %d already present (embeddings %s)",
            created,
            len(existing_titles),
            "enabled" if llm._get_client() else "disabled — GEMINI_API_KEY not set, using MITRE-overlap fallback",
        )


async def seed_demo_data() -> None:
    async with session_scope() as session:
        existing = (
            await session.execute(select(User).where(User.email == DEMO_EMAIL))
        ).scalar_one_or_none()
        if existing:
            logger.info("Demo user already exists (%s); skipping demo data seed", DEMO_EMAIL)
            return

        user = User(email=DEMO_EMAIL, password_hash=hash_password(DEMO_PASSWORD))
        session.add(user)
        await session.flush()

        device = Device(user_id=user.id, browser="Chrome 124", os="Windows 11")
        session.add(device)
        await session.flush()

        event = Event(
            device_id=device.device_id,
            event_type=EventType.URL_VISIT,
            payload_json={"url": "http://amaz0n-login-security-verify.tk/account/confirm"},
        )
        session.add(event)
        await session.flush()

        incident = Incident(
            user_id=user.id,
            title="Credential Theft Attempt",
            severity=IncidentSeverity.HIGH,
            confidence=0.87,
            mitre=["T1566", "T1566.002", "T1056.003"],
            status=IncidentStatus.OPEN,
            summary=(
                "Credential Theft Attempt. Triggered by: DistilBERT flagged a brand-impersonation "
                "domain; VirusTotal confirmed malicious reputation."
            ),
        )
        session.add(incident)
        await session.flush()

        session.add(
            Evidence(
                incident_id=incident.incident_id,
                event_id=event.event_id,
                reason="Phishing model flagged amaz0n-login-security-verify.tk (91% confidence)",
                score=0.91,
            )
        )

        logger.info("Seeded demo user (%s / %s), device, and one sample incident", DEMO_EMAIL, DEMO_PASSWORD)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-demo-data", action="store_true", help="Only seed playbooks, skip demo user/incident")
    args = parser.parse_args()

    logger.info("Ensuring database schema exists...")
    async with engine.begin() as conn:
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"'))
        await conn.run_sync(Base.metadata.create_all)

    await seed_playbooks()

    if not args.skip_demo_data:
        await seed_demo_data()

    logger.info("Seed complete.")


if __name__ == "__main__":
    asyncio.run(main())
