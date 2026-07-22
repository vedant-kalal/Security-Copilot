# Folder Structure

```
sentinelai/
├── README.md                        Start here
├── .gitignore
│
├── backend/                               FastAPI application
│   ├── requirements.txt
│   ├── .env.example
│   ├── alembic.ini                          Alembic config (points at migrations/)
│   ├── pytest.ini
│   ├── migrations/
│   │   ├── env.py                             Alembic runtime — loads Settings + all models
│   │   └── versions/0001_initial_schema.py       Hand-written migration: all 9 tables, enums, indexes, pgvector ext
│   ├── model_artifacts/                     Trained Isolation Forest (.joblib) — regenerate via scripts/train_isolation_forest.py
│   ├── app/
│   │   ├── main.py                              FastAPI app factory, middleware wiring, /health
│   │   ├── core/
│   │   │   ├── config.py                          Settings (env-var driven, pydantic-settings)
│   │   │   ├── security.py                          Password hashing, JWT issuance/verification
│   │   │   ├── logging.py                             Structured JSON (prod) / colored (dev) logging
│   │   │   ├── exceptions.py                           Domain exception hierarchy
│   │   │   └── database.py                               Async SQLAlchemy engine/session
│   │   ├── models/                              SQLAlchemy ORM (one file per table)
│   │   ├── schemas/                             Pydantic request/response contracts
│   │   ├── repositories/                        DB query layer (one per table/aggregate)
│   │   ├── services/                              Business logic — see docs/ARCHITECTURE.md for the full list
│   │   │   ├── correlation_service.py               ★ Threat Correlation Engine
│   │   │   ├── incident_service.py                     ★ Pipeline orchestration + incident CRUD
│   │   │   ├── phishing_service.py, threat_intel_service.py, anomaly_service.py
│   │   │   ├── rag_service.py, llm_service.py            RAG + Gemini
│   │   │   ├── mitre_service.py, dashboard_service.py, network_service.py
│   │   │   ├── auth_service.py, device_service.py, event_service.py
│   │   ├── ml/
│   │   │   ├── phishing_model.py                       DistilBERT wrapper + heuristic fallback
│   │   │   ├── anomaly_model.py                          Isolation Forest wrapper + bootstrap fallback
│   │   │   └── feature_engineering.py                      Shared feature vector (train + inference)
│   │   ├── api/v1/                              Routers — one file per resource, thin (delegate to services)
│   │   ├── middleware/                          Error handling, request logging, rate limiting
│   │   ├── utils/
│   │   │   ├── mitre_mappings.py                       Curated MITRE ATT&CK reference + signal→technique map
│   │   │   └── validators.py                             URL/domain/IP helpers
│   │   └── data/
│   │       ├── playbooks/playbooks.json                 8 seed playbooks (RAG source content)
│   │       └── network_datasets/*.csv                     Sample CICIDS2017/UNSW-NB15-style replay data
│   └── tests/                                 pytest suite — see docs/TESTING.md
│
├── dashboard/                              React + Vite + TypeScript investigation UI
│   ├── package.json, vite.config.ts, tailwind.config.ts, tsconfig*.json
│   └── src/
│       ├── main.tsx, App.tsx, router.tsx
│       ├── lib/
│       │   ├── api-client.ts                          Typed fetch wrapper, JWT + refresh-on-401
│       │   ├── mitre.ts                                  Local MITRE reference for tooltips
│       │   └── utils.ts, constants.ts
│       ├── context/AuthContext.tsx
│       ├── hooks/                                     useAuth, useDashboard, useIncidents
│       ├── types/index.ts                              Local copy of the API's TS types
│       ├── components/
│       │   ├── ui/                                       Restyled shadcn-pattern primitives
│       │   ├── layout/                                     Sidebar, Topbar, DashboardLayout
│       │   ├── dashboard/                                   SecurityScoreGauge (signature radar dial), StatsGrid, RecentThreats
│       │   ├── incidents/                                     IncidentTable, EvidenceList, IncidentTimeline, AIExplanation, PlaybooksDialog
│       │   └── network/                                         CsvUpload, ReplayControl
│       └── pages/                                     One component per route (see router.tsx)
│
├── extension/                                Chrome Manifest V3 extension
│   ├── manifest.json
│   ├── vite.config.ts, vite.content.config.ts       Two build passes — see extension/README.md
│   ├── scripts/copy-assets.mjs                        Post-build: flatten HTML output, copy manifest+icons
│   └── src/
│       ├── background/index.ts                          Service worker: navigation/download watching, heartbeat
│       ├── content/index.ts                               Dependency-free content script (password-form detection)
│       ├── popup/                                          Popup UI (risk verdict + action buttons)
│       ├── options/                                          Settings UI (auth, API URL)
│       ├── lib/                                              storage.ts, api.ts, auth.ts
│       └── types/index.ts
│
├── shared/                                     Cross-package TS reference (types/api.ts, utils/*)
│
├── database/
│   ├── schema.sql                                Generated DDL reference (via scripts/export_schema.py)
│   └── seed_data.sql                               Illustrative SQL sample data
│
├── scripts/
│   ├── train_isolation_forest.py                   Fit the anomaly model on a traffic baseline
│   ├── seed_db.py                                     Seed playbooks (+ embeddings) and demo data
│   └── export_schema.py                                Regenerate database/schema.sql from the ORM models
│
└── docs/
    ├── ARCHITECTURE.md, API.md, INSTALLATION.md, DEPLOYMENT.md, DEVELOPER_GUIDE.md, TESTING.md, FOLDER_STRUCTURE.md (this file)
```

`★` marks the two files most worth reading first to understand how the product actually works:
`backend/app/services/correlation_service.py` and `backend/app/services/incident_service.py`.
