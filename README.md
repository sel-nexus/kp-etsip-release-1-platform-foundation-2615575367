# KP ETSIP — platform foundation

KP ETSIP provides local identity and My Profile; portfolio and application inventory with search, filters and scoped changes; an executive dashboard and inventory reports with CSV export; and user, role and audit administration. The API uses async PyMongo and requires a real MongoDB instance.

Access is role- and permission-dependent: a Portfolio Leader sees only assigned portfolios, and an empty assignment grants access to none. Administrators manage accounts and role permissions within role ceilings; users are deactivated rather than erased. Auditors have separately authorized audit read/export access, not user or role administration. Portfolio deletion is blocked by linked applications or account assignments. Authentication is local; there is no public signup.

## Configuration and local run

1. Install Python 3.12+, Node 20+, and start MongoDB. Copy `backend/.env.example` to `backend/.env` and `frontend/.env.example` to `frontend/.env` if not already present. These runtime files are ignored by Git.
2. Set `JWT_SECRET` in `backend/.env` to an independently generated random secret of at least 32 characters (for example `python -c 'import secrets; print(secrets.token_urlsafe(48))'`). The server rejects the example secret. Set `SEED_PASSWORD` to your chosen initial demo password (12–72 UTF-8 bytes). Replace both for deployment and protect them as secrets. Seed credentials are never reset on subsequent starts.
3. From `backend`, create a virtual environment and install with `python -m pip install -r requirements.txt`; start with `python -m uvicorn app.main:app --reload`.
4. From `frontend`, run `npm install` then `npm run dev`. The dev server proxies `/api` to `VITE_PROXY_TARGET` and serves at `http://localhost:5173`.

The six seeded accounts are `admin@ketsip.local`, `executive@ketsip.local`, `leader@ketsip.local`, `engineer@ketsip.local`, `auditor@ketsip.local`, and `readonly@ketsip.local`. Their initial password is the configured `SEED_PASSWORD` (example: `DemoPassword123!`). Every account must change that password at first sign-in. After any password change, all prior tokens are invalidated and a fresh sign-in is required. Administrators can create accounts with an initial password; there is no public signup.

Startup seeding is enabled by default (`SEED_ON_STARTUP=true`): it inserts missing demo roles, accounts, portfolios and applications without resetting existing credentials or role settings. It is not a transactional migration: interruption or concurrent starts can leave partial data or reservations, and deleted demo records may be recreated on a later start. Disable startup seeding (`SEED_ON_STARTUP=false`) where demo data or its recreation is unwanted, and review existing data before changing this setting.

## Containers

With `backend/.env` configured as above, run `docker compose up --build -d`. Open `http://localhost:8080`. Compose persists MongoDB in `mongo_data`. Terminate using `docker compose down`; do not add `-v` unless deliberately deleting all data. The included standalone Mongo container is for local development; secure the database and use TLS, authentication, backups, and HTTPS at the deployment boundary in production. Never use the demonstration password or JWT secret in production.

## API

`POST /api/auth/login` accepts `email` and `password`, returning `{token,user}`; `GET /api/auth/me`, `POST /api/auth/logout`, `PUT /api/auth/profile` (`defaultLandingPage`: `dashboard` or `applications`), and `POST /api/auth/password` (`currentPassword`, `newPassword`) require `Authorization: Bearer <token>`. `/api/health` is a dependency-free liveness exception. The profile preference endpoint requires the initial password to have been changed. Sign-out clears the browser's session token; the stateless logout endpoint itself does not revoke a copied token, which remains valid until expiry or credential change. Password hashes never appear in responses. OpenAPI documentation is available at `/docs`.

Other API surfaces include `/api/portfolios`, `/api/applications` (including `/export`), `/api/users`, `/api/roles`, `/api/audit-logs`, `/api/dashboard/executive`, and `/api/reports/{applications|portfolios}`. Inventory and reports are scoped to the caller's role and permissions. List responses are bounded; audit CSV exports a bounded page, while inventory report CSV exports the filtered selection. See `/docs` for methods, filters and schemas.

## Operational limits and manual reconciliation

Application and account-assignment writes use portfolio reservation tokens to prevent deletion racing with new references. Portfolio deletion uses a `deletionLock` and checks both applications and user assignments. These are separate MongoDB writes, not a multi-document transaction: a crash, timeout or ambiguous result can leave a reservation or lock behind, and a reported error does not prove that a write failed. Audit entries are separate writes too: a mutation may succeed even if its audit write fails or the response reports an error. Do not treat the audit log as a complete transactional ledger or blindly retry an uncertain mutation.

If deletion is blocked unexpectedly or an operation has an uncertain outcome, have a qualified MongoDB operator reconcile it conservatively:

1. Stop **all writers** to the affected database, including every API instance, startup seeding, jobs, scripts and direct database clients. Ensure in-flight operations have finished and the database has reached a stable state; do not restart writers during investigation. Identify the correct MongoDB deployment and database and take a verified backup before any repair.
2. Inspect the actual MongoDB `portfolios` documents, including `_id`, `applicationReservations` and `deletionLock` (these internal fields are omitted from normal API responses). Compare each affected portfolio's ID with `applications.portfolioId` and `users.portfolioAccess`, including case variants, and inspect each application's `reservation` token against the corresponding portfolio's token array. Record the exact tokens, references, account assignments, timestamps, relevant logs and uncertain operation outcomes. Assignment reservations are temporary and are not stored on user documents, so an unmatched token alone does not establish that it is safe to remove.
3. Determine whether each create, move, delete or assignment actually committed, including whether a portfolio delete is still uncertain. A live application's matching reservation protects its reference and must not be removed. Check missing portfolios, mismatched tokens and references, and any audit gaps against independent evidence; absence of an audit entry is not proof of failure. Never blindly clear all reservations or locks, infer safety merely from age, or retry the operation while its outcome is ambiguous.
4. Only after the responsible operator has established that no write is in flight and the particular token or lock is stale, and has an approved, evidence-based repair for that specific state, make a targeted change while writers remain stopped. Preserve valid references and reservations, re-read the affected documents and verify application references, account assignments and token/lock consistency before allowing writes again. Keep the backup and a record of the decision and changes. If ownership, outcome or safe repair is uncertain, leave the protection in place and escalate to the database/application owner; do not guess.

This is conservative manual guidance, not a tested automatic recovery procedure. A lock or reservation may intentionally remain until an operator can resolve the underlying ambiguity.

## Tests

Run the complete backend suite against a real, isolated MongoDB instance. Install `backend/requirements.txt` in your virtual environment, start MongoDB, and set `TEST_MONGODB_URI` if it is not available at the default `mongodb://localhost:27017`. Use a disposable test instance, not a production database. Each test creates a uniquely named `ketsip_test_...` database and normally drops it during fixture cleanup; an interrupted run or setup failure may leave a test database behind.

From `backend`, with the virtual environment activated, run:

```sh
PYTHONPATH=. python -m pytest -q
```

Frontend component tests run from `frontend` with `npm test`; type-check and build with `npm run build`. Browser journeys can be run against a disposable database as described below.

### Browser E2E setup

The suite changes accounts, passwords, preferences, inventory and other records. Use a **separate disposable MongoDB instance**, never a development, shared or production instance. Install the backend and frontend dependencies and Playwright Chromium first. Leave ports 8000 and 5173 free: Playwright starts both servers itself and refuses to reuse existing servers. It forces the Vite API proxy to its own backend and overrides the backend's MongoDB settings, seed password and JWT secret; `backend/.env` cannot select the E2E database.

From `frontend`, set the following in a POSIX shell (adjust the Mongo URI only to your dedicated disposable instance):

```sh
export E2E_MONGODB_URI='mongodb://127.0.0.1:27017'
export E2E_MONGODB_DB="ketsip_e2e_$(python3 -c 'import secrets; print(secrets.token_hex(8))')"
export E2E_DISPOSABLE_DB="$E2E_MONGODB_DB"
export E2E_INITIAL_PASSWORD='DemoPassword123!'
export E2E_NEW_PASSWORD='ChangedPassword456!'
unset E2E_EMAIL E2E_READONLY_INITIAL_PASSWORD
# Optionally set E2E_PYTHON to the backend virtual environment's Python executable.
node node_modules/@playwright/test/cli.js test
```

Confirm that the URI actually points to the dedicated instance before running; the name and confirmation variable are safeguards, not proof of isolation. Use a **new, empty database name for every complete run**, including retries after an interruption. Startup seeds the fresh database using `E2E_INITIAL_PASSWORD`; it does not reset existing accounts or credentials, and the identity project must run before the dependent journeys. The initial and replacement passwords must be different. The default administrator and read-only accounts are expected by the suite. Do not run concurrent suites against the same database. The harness does not drop databases; when finished, an operator may remove only the explicitly identified disposable E2E database or destroy the dedicated disposable instance, never development data.
