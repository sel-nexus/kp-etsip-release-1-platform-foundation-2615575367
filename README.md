# KP ETSIP — identity foundation

This slice provides local identity and My Profile. Inventory, dashboards and administration are future slices; their landing routes clearly indicate they are not yet available. The API uses async PyMongo and requires a real MongoDB instance.

## Configuration and local run

1. Install Python 3.12+, Node 20+, and start MongoDB. Copy `backend/.env.example` to `backend/.env` and `frontend/.env.example` to `frontend/.env` if not already present. These runtime files are ignored by Git.
2. Set `JWT_SECRET` in `backend/.env` to an independently generated random secret of at least 32 characters (for example `python -c 'import secrets; print(secrets.token_urlsafe(48))'`). The server rejects the example secret. Set `SEED_PASSWORD` to your chosen initial demo password (12–72 UTF-8 bytes). Replace both for deployment and protect them as secrets. Seed credentials are never reset on subsequent starts.
3. From `backend`, create a virtual environment and install with `python -m pip install -r requirements.txt`; start with `python -m uvicorn app.main:app --reload`.
4. From `frontend`, run `npm install` then `npm run dev`. The dev server proxies `/api` to `VITE_PROXY_TARGET` and serves at `http://localhost:5173`.

The six seeded accounts are `admin@ketsip.local`, `executive@ketsip.local`, `leader@ketsip.local`, `engineer@ketsip.local`, `auditor@ketsip.local`, and `readonly@ketsip.local`. Their initial password is the configured `SEED_PASSWORD` (example: `DemoPassword123!`). Every account must change that password at first sign-in. After any password change, all prior tokens are invalidated and a fresh sign-in is required. A Portfolio Leader with no assignments has access to no portfolios. No account creation or signup is provided in this slice.

## Containers

With `backend/.env` configured as above, run `docker compose up --build -d`. Open `http://localhost:8080`. Compose persists MongoDB in `mongo_data`. Terminate using `docker compose down`; do not add `-v` unless deliberately deleting all data. The included standalone Mongo container is for local development; secure the database and use TLS, authentication, backups, and HTTPS at the deployment boundary in production. Never use the demonstration password or JWT secret in production.

## API

`POST /api/auth/login` accepts `email` and `password`, returning `{token,user}`; `GET /api/auth/me`, `POST /api/auth/logout`, `PUT /api/auth/profile` (`defaultLandingPage`: `dashboard` or `applications`), and `POST /api/auth/password` (`currentPassword`, `newPassword`) require `Authorization: Bearer <token>`. `/api/health` is a dependency-free liveness exception. The profile preference endpoint requires the initial password to have been changed. Sign-out clears the browser's session token; the stateless logout endpoint itself does not revoke a copied token, which remains valid until expiry or credential change. Password hashes never appear in responses. OpenAPI documentation is available at `/docs`.

## Tests

The backend tests create a uniquely named isolated database on `TEST_MONGODB_URI` (default `mongodb://localhost:27017`) and drop only that database afterward. Run `cd backend && PYTHONPATH=. "$HOME/venvs/app/bin/python" -m pytest -q tests/test_auth.py`. Frontend component tests run from `frontend` with `npm test`; type-check and build with `npm run build`. E2E specs are written but deferred. Run later against running services using `node node_modules/@playwright/test/cli.js test` from `frontend`; use a disposable, fresh database and set `E2E_EMAIL`, `E2E_INITIAL_PASSWORD` and `E2E_NEW_PASSWORD` if needed. The E2E journey changes the selected account's password and preference.
