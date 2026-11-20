# Start Here — HeatShield AI v0.5.3

1. Install Python dependencies from `backend/requirements.txt`.
2. Copy `backend/.env.example` to `backend/.env`. Add a private provider key only if BioTwin LLM responses are required. Never commit `.env`.
3. Start the API from `backend/` with `python -m uvicorn app.main:app --reload --port 8000`.
4. From the project root, run `npm ci` and `npm run dev`.
5. Open the local Vite URL. The API defaults to `http://localhost:8000`.
6. Before any deployment, run backend tests and `npm ci && npm run build`. Review the deployment gates in `V0.5.1_HARDENING_NOTES.md`.

The bundled database includes 2 worksites, 4 zones, 6 registered worker records, 6 exposure records labelled `demo_simulation`, and 2 recommended interventions. The offline-alert queue is empty. The Abu Dhabi pilot worksite has 6 registered worker records, but its declared `worker_count` field is 0; this distinction is preserved pending confirmation. Do not interpret simulated exposure records as live sensor measurements, and do not treat missing data as safe.

## Secure sign-in (v7)
Start the backend and frontend as usual. The application now opens at a sign-in screen.
The bundled database already contains an administrator account, so its existing password is retained and the first-run demo password may not work. Use the administrator password previously configured for this database. The demo credentials `admin@heatshield.ai` / `ChangeMe123!` are only used when a completely empty database bootstraps its first administrator. Do not reset or replace the existing account without a verified backup. Before deployment, set `HEATSHIELD_AUTH_SECRET` to a long random secret and configure the bootstrap administrator credentials in `backend/.env`. See `AUTHENTICATION_AND_PORTAL_RELEASE_NOTES_v7.md` for limitations and deployment hardening requirements.
