# HeatShield AI — Integrated Prototype v0.5.3

HeatShield AI is a modular occupational heat-exposure intelligence prototype with six workspaces: AuraHeat, EquiClimate, BioTwin, BioShield Mesh, Preventive Care, and Analytics & Reports.

## Security and role access\n\nOperational API groups enforce server-side role checks, and protected requests re-check account activation and the current role. User administration is administrator-only; BioTwin is limited to administrators/researchers; Mesh to administrators/supervisors; worksite/workforce writes to administrators/supervisors (health-safety can register workers); and exposure/risk/intervention workflows to administrators/supervisors/health-safety users. Executive and health-safety roles can read operational lists needed by their workspaces. This is a prototype permission baseline, not a complete per-worksite authorization or worker-identity isolation system.\n\nThe weather catalogue includes Abu Dhabi, Dubai, Sharjah and Al Ain using UAE local time, while retaining the existing Pakistan city options. Weather data remains forecast context, not measured WBGT.\n\n## Module sign-in entry points

The shared sign-in component supports workspace-specific entry URLs, including `/login/auraheat`, `/login/equiclimate`, `/login/biotwin`, `/login/mesh`, `/login/preventive`, `/login/analytics`, `/login/workforce`, `/login/worksites`, `/login/worker`, `/login/overview`, and `/login/admin-users`. Each entry validates the account role before opening the requested workspace. Authentication remains centralized to avoid duplicate credential systems.

## Run locally

### Backend

```bash
cd backend
python -m pip install -r requirements.txt
# Copy .env.example to .env and add a provider key only if using BioTwin LLM responses.
python -m uvicorn app.main:app --reload --port 8000
```

The API uses `backend/heatshield.db` by default. The bundled database currently contains 2 worksite records, 4 zones, 6 registered worker records, 6 exposure records explicitly labelled `demo_simulation`, and 2 recommended interventions. The offline-alert queue is empty. One worksite is an unconfigured placeholder; the Abu Dhabi pilot worksite has 6 registered worker records while its separately stored declared `worker_count` remains 0. These values are preserved as received; do not silently reconcile the declared count without confirming what it represents.

For a deployed frontend, set `HEATSHIELD_CORS_ORIGINS` in `backend/.env` to a comma-separated list of exact trusted frontend origins. Do not use wildcard origins with credentials or expose the API publicly without authentication and access controls.

### Frontend

```bash
npm ci
npm run dev
```

Set `VITE_API_BASE_URL` if the API is not running at `http://localhost:8000`.

### Production build

```bash
npm ci
npm run build
```

The build was not verified in this packaging environment: `npm ci` timed out and package-registry access was unavailable. Do not deploy until the production build succeeds in the target environment.

## Tests

From the `backend` directory:

```bash
python -m compileall -q app
python -m unittest app.knowledge.test_knowledge app.test_api_smoke -v
```

The API smoke tests exercise health/dashboard, unknown exposure states, measured-WBGT provenance validation, intervention state transitions, offline alert queue/sync, and rejection of unregistered worker codes. The test suite stubs the optional Groq SDK import because these tests do not call the LLM provider.

## Module overview

- **AuraHeat:** worker registration, exposure-record entry, recorded exposure visibility, prototype exposure screening and rest-zone rotation suggestions. Worker and exposure forms write to the backend API.
- **EquiClimate:** worksite and zone creation, worksites/zones overview, measured-vs-estimated WBGT provenance, and a zone relationship schematic. The schematic is not a spatially accurate digital twin without site coordinates/floor plans.
- **BioTwin:** biomedical/occupational evidence retrieval and Chronic Health Intelligence research support.
- **BioShield Mesh:** backend device-state reporting and queued offline-alert workflow simulation. No physical hardware integration is included.
- **Preventive Care:** create intervention recommendations and manage approve, dismiss and complete transitions through the backend API.
- **Analytics & Reports:** descriptive operational counts, exposure-entry trends and CSV export.

## Safety, privacy and interpretation

HeatShield is a prototype decision-support system, not a medical device or validated occupational-safety assessment. The backend exposure heuristic is experimental and must not be used as a medical score, disease probability, diagnosis, or fitness-for-work decision. Missing, stale or failed data is unknown, never safe. Weather-derived conditions are not on-site WBGT measurements. Only records explicitly sourced from `onsite_sensor` can populate measured WBGT.

The bundled dataset does not contain verified personal health records or real-time sensor data. Consequently, the system does not estimate individual chronic disease onset/progression probabilities. BioTwin retrieves and explains indexed research evidence, including evidence gaps, without inferring individual causation.

**Before real-world deployment:** add authenticated identities, role-based authorization, consent and access controls for health data, encrypted transport/storage, audit logging, incident response, jurisdiction-specific occupational-safety review, clinical/occupational-health validation, and real sensor integration with calibration/freshness monitoring. Do not enter identifiable worker medical data into this prototype until those controls exist.

See `V3_RELEASE_NOTES_2026-11-17.md`, `V0.5.1_HARDENING_NOTES.md`, and `V5_FINAL_INTEGRATION_NOTES_2026-11-17.md` for implementation detail, verification results and remaining external dependencies.
\n\nSee `V0.5.3_AUDIT_AND_INTEGRATION_HARDENING.md` for the latest audit changes, test results and remaining release gates.\n

## Submission integration addendum — 2026-11-19

- Preserved the uploaded v2 sage/forest-green and lime visual theme, navigation, authentication shell and existing portal files.
- Added a BioTwin Worker Health Intelligence directory with worker-ID/domain search and domain filtering.
- Added `worker_health_demo_profiles` to SQLite and six explicitly synthetic example profiles linked only to existing `SIM-WKR-001`…`SIM-WKR-006` demo identities at the Abu Dhabi pilot worksite. Inserts are idempotent (`INSERT OR IGNORE`).
- Added authenticated `GET /api/biotwin/worker-health-demo`; it inherits the existing BioTwin admin/researcher role gate.
- Worker health profile labels are fictional examples, not diagnoses or predictions. Exposure band, temperature, humidity and duration remain environmental context. Demo exposure rows remain excluded from the existing worker risk scoring. No WBGT or physiological vitals are fabricated.
- Hardened BioTwin answer cleanup for HTML `<br>`/paragraph tags, Markdown emphasis/headings, citation tokens and duplicate/empty summary fragments; evidence lists tolerate malformed non-array payloads and alternate answer/evidence response fields.
- Validation in this environment: Python compile passed; existing backend/knowledge tests 18/18 passed; additional authenticated worker-health endpoint smoke test passed; all `src/*.js` and `src/*.jsx` transpile/parse checks passed; SQLite integrity check passed.
- Not verified: `npm ci` / Vite production build and browser E2E could not be run because frontend dependencies are not installed in this environment. Do not claim production build or live browser testing passed.
- Remaining production gates from the original checklist still apply: per-worksite isolation, health-data consent/governance, secure session/cookie strategy, secret provisioning/rotation, audit logging, hardware calibration/integration and clinical/occupational-health validation.
