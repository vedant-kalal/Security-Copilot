# shared/

Cross-package reference code for the dashboard and extension:

- `types/api.ts` — canonical TypeScript types mirroring the backend's Pydantic schemas.
- `utils/constants.ts` — shared display labels (severity, status).
- `utils/mitre.ts` — curated MITRE ATT&CK reference, mirroring `backend/app/utils/mitre_mappings.py`.

`dashboard/` and `extension/` are independent Vite projects with their own dependency trees, so each currently
vendors a small local copy of the types/constants it needs (see `dashboard/src/types/index.ts` and
`extension/src/types/index.ts`) rather than importing across package boundaries — this keeps each package's
build self-contained with zero cross-project path config. This folder is the canonical source those local
copies are kept in sync with. If the project grows into a proper npm workspace/monorepo, wiring both apps to
import directly from here is the natural next step.
