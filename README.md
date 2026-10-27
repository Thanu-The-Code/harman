# Paperless Factory — Quality Records (A Harman Product)

Paperless Factory replaces paper quality records on the shop floor.

- Blank quality **formats** (inspection sheets, check sheets) live on the server.
- **Process Owners** fill them digitally, with each reading checked against its specification as it is typed.
- Every record then moves through a fixed approval chain:

```
Process Owner ─► Overall Process Owner ─► Quality CFT joint review ─► Final decision ─► Filed on server
```

- Out-of-spec (N-OK) readings raise a flag to the Overall Process Owner.
- Every record carries a tracking colour: 🟢 OK for final review, 🟡 filling in progress, 🔴 needs re-verification with CFT.
- Approved records are filed in date-wise / month-wise folders according to how often the format is filled.
- Changing a released format goes through a **Document Change Request** approved by the QMS Coordinator.

The process is defined in [Project Core Workflow.pdf](Project%20Core%20Workflow.pdf). The plan to connect the frontend to the backend is in **[INTEGRATION_PLAN.md](INTEGRATION_PLAN.md)**.

---

## Repository layout

```
Harman/
├── BE/                                  FastAPI backend (API, workflow engine, PDFs, email)
│   ├── app/
│   │   ├── main.py                      app factory, CORS, middleware, startup
│   │   ├── routers/                     ~95 endpoints under /api/* (see routers/api.py)
│   │   ├── services/                    business logic: record_service, workflow_service,
│   │   │                                format_service, approval_route, change_request_service,
│   │   │                                notification_service, form_layout, evidence_service …
│   │   ├── ocr/                         document import: Excel / PDF / image of a form -> template
│   │   │                                elements (format registry, grid interpreter, PaddleOCR engine)
│   │   ├── models.py, models_qms.py     SQLAlchemy models (users, workflows, formats, records …)
│   │   ├── middleware/                  error envelope, logging, rate limiting
│   │   └── config.py                    settings (env / .env / DB settings table)
│   ├── scripts/                         seed_quality_records.py, validate_workflow.py, reset_demo.py …
│   ├── tests/                           pytest suite (in-memory SQLite); tests/ocr: the OCR suite and
│   │                                    the client's sample forms (samples/client: Excel, PDF, JPG)
│   ├── cli.py                           init / serve / users / db / backup commands
│   ├── .env.example                     configuration template
│   ├── requirements.txt                 incl. Excel import; requirements-ocr.txt adds PDF / image OCR
│   └── Dockerfile, setup.ps1, setup.sh, run.sh
├── FE/harman-paperless-factoryFE-main/  React frontend
│   ├── src/
│   │   ├── App.tsx                      routes (lazy-loaded screens, auth / admin guards)
│   │   ├── api/                         RTK Query endpoints per domain (*.api.ts), error parser, session
│   │   ├── helpers/index.ts             axios instance + auth interceptors
│   │   ├── redux/store.ts               store (the RTK Query cache)
│   │   ├── login, dashboard, resources, myForms, myApprovals, templateBuilder,
│   │   │   templateRepo, docRepository, changeRequest, peopleAndTeams,
│   │   │   activityLog, header (notifications, settings), sidebar, base (shared UI)
│   │   ├── templateBuilder/designer/    the Figma designer: canvas, Add Fields / Field Properties,
│   │   │                                text toolbar, Create Template, Upload File, Continue step
│   │   ├── vendor/react-form-builder/   the form builder library (react-form-builder2 0.20.3 with a
│   │   │                                Table element and OCR views), kept as source and extended here
│   │   └── hooks/, utils/, constants/   shared hooks (authed files, debounce), IST dates, view types
│   ├── vite.config.ts                   dev proxy /api → VITE_API_URL
│   └── Dockerfile, nginx.conf
├── Project Core Workflow.pdf            business process
├── INTEGRATION_PLAN.md                  FE ↔ BE integration plan (step by step)
└── README.md                            this file
```

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Pydantic Settings, JWT (python-jose) + session cookie, bcrypt, ReportLab / PyPDF2 / pypdfium2 (PDFs and signature stamping), SMTP email |
| Database | PostgreSQL (default; production and CI) or SQLite (quick local runs, tests) |
| Frontend | React 19, TypeScript, Vite 8, MUI 9, Redux Toolkit 2, AG Grid / AG Charts, react-form-builder2 (template designer), axios, react-toastify |
| Delivery | Docker images; GitHub Actions deploy (BE on branch `harman-dev`, FE on `main`); FE served by nginx |

## Who does what (workflow roles)

The workflow roles are assigned **per format** in the template builder. RBAC roles (Roles & Permissions screen) only grant capabilities: view, fill records, create templates, approve.

| Role | Responsibility in the app |
|---|---|
| Administrator | Builds templates, submits them for release approval, manages people, teams, roles |
| Process Owner (PO) | Calls a format, fills the record, approves step 1, takes the final decision, can send a record back to CFT |
| Overall Process Owner (OPO) | Approves step 2, clears N-OK flags, files approved records |
| Quality CFT members | Joint review: each member agrees or objects, before the target date |
| QMS Coordinator | Reviews, approves and executes Document Change Requests (new revision or new format) |

---

## Prerequisites

- **Python 3.12**. On Windows you also need `python-magic-bin`; see below.
- **Node.js ≥ 20.19 or ≥ 22.12** (Vite 8) and npm.
- **PostgreSQL 14+**. Optional for local development: SQLite works.
- Optional: an SMTP server. Without it, notifications are stored and shown in-app with status `skipped`.

## Quick start (local development)

### 1. Backend — Windows (PowerShell)

```powershell
cd BE
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pip install python-magic-bin==0.4.14        # Windows only: libmagic binaries
.venv\Scripts\pip install -r requirements-ocr.txt         # optional: read PDFs / scans into templates (~1 GB)
Copy-Item .env.example .env
```

Edit `BE\.env` for local development:

```ini
ENVIRONMENT=development                 # .env.example says production -> Secure cookies won't work on http://localhost
AUTHENTICATION_ENABLED=true             # false = every request runs as the admin (no real users)
SECRET_KEY=<any long random string>
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000
APP_BASE_URL=http://localhost:5173      # where links in emails point
# Quickest: SQLite. Or set DATABASE_HOST/PORT/NAME/USER/PASSWORD for PostgreSQL.
DATABASE_URL=sqlite:///./data/documents.db
```

Then initialise, seed and run:

```powershell
.venv\Scripts\python cli.py init                          # create tables + default settings
.venv\Scripts\python scripts\seed_quality_records.py      # demo users, teams, formats, records
.venv\Scripts\python cli.py serve                         # http://127.0.0.1:8000  (Swagger: /docs)
```

### 1. Backend — Linux / macOS

```bash
cd BE
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -r requirements-ocr.txt             # optional: PDF / image OCR (needs libgl1, libgomp1)
cp .env.example .env                                      # edit as above
.venv/bin/python cli.py init
.venv/bin/python scripts/seed_quality_records.py
./run.sh                                                  # or: .venv/bin/python cli.py serve
```

### 2. Frontend

```bash
cd FE/harman-paperless-factoryFE-main
npm ci
```

Point the dev proxy at your local backend. The committed `.env` points at the **production** API. Create `.env.development.local` (not committed):

```ini
VITE_API_URL=http://127.0.0.1:8000
```

Then start the dev server:

```bash
npm run dev                                               # http://localhost:5173  (/api/* is proxied to VITE_API_URL)
```

### 3. Log in

The seed creates these users, all with password **`Harman@2026`**:

| Username | Person | Role in format QF-PQ-001 |
|---|---|---|
| `admin` | System Administrator | builds and releases formats |
| `r.kumar` | Ravi Kumar | Process Owner |
| `s.iyer` | Sunita Iyer | Overall Process Owner |
| `a.deshmukh`, `p.nair` | Anil Deshmukh, Priya Nair | CFT members |
| `m.shaikh` | Mohammed Shaikh | QMS Coordinator |
| `a.sharma` | Aryan Sharma | Process Owner – Assembly |
| `k.reddy`, `d.varma` | Kavitha Reddy, Deepak Varma | PO / OPO for QF-SQ-002 |

On a fresh database **without** the seed there are no users. Create the first admin with `POST /api/auth/setup/initial-user` (allowed only while there are zero users).

> **Roles matter (INTEGRATION_PLAN.md B1/B14):** on every backend start, non-admin users without a custom role lose their approve and sign rights. The seed gives every seeded person the **"Quality Approver"** role so their rights survive restarts. Users you create yourself need a role with the *Approval* capability. Note that this capability currently also lets the holder file any record (B14).

---

## Important commands

### Backend (`BE/`)

| Command | What it does |
|---|---|
| `python cli.py init` | Create tables, apply column migrations, write default settings |
| `python cli.py serve` | Run the API with auto-reload on `DOCUMENT_MANAGER_HOST:DOCUMENT_MANAGER_PORT` (default `127.0.0.1:8000`) |
| `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000` | Run without the CLI wrapper |
| `python scripts/seed_quality_records.py` | Seed demo users, quality teams (PQ/SQ/CQ), three formats and sample records |
| `python scripts/validate_workflow.py [--url http://127.0.0.1:8000] [--quick]` | End-to-end workflow check against a **running** server, logging in as the seeded users |
| `python scripts/check_frontend_contract.py [http://127.0.0.1:5173]` | Replays every frontend request (same payloads) against a running system: templates, filling, the approval chain, repository, change requests, people, dashboard, notifications, access control (144 checks). Point it at :5173 (through the Vite proxy) or :8000. It creates data, so re-seed afterwards |
| `python -m pytest tests -q` | Unit/API tests (in-memory SQLite). The OCR suite (`tests/ocr`) runs its Excel, registry and HTTP tests; the OpenCV ones need `requirements-ocr.txt` |
| `RUN_OCR_TESTS=1 python -m pytest tests/ocr -q` | Also the PaddleOCR tests: templates from the client's PDFs, filling from scans with handwriting (~5 min on a CPU) |
| `python cli.py users` | List user accounts |
| `python cli.py reset-password <username>` | Reset a password |
| `python cli.py db analyze \| optimize \| create-indexes \| size` | Database maintenance |
| `python cli.py backup create \| list \| restore` | Backups |
| `python scripts/reset_demo.py` | Reset demo data (**SQLite only**: deletes `data/documents.db`) |

On Windows, prefix the Python commands with `.venv\Scripts\`, and on Linux with `.venv/bin/`.

Useful URLs while the backend runs:

- `http://127.0.0.1:8000/docs`: Swagger UI.
- `/openapi.json`: the OpenAPI schema.
- `/health` and `/api/health/simple`: health checks.

### Frontend (`FE/harman-paperless-factoryFE-main/`)

| Command | What it does |
|---|---|
| `npm ci` | Install exact dependency versions |
| `npm run dev` | Vite dev server on :5173 with the `/api` proxy |
| `npm run build` | Type-check (`tsc -b`) and build to `dist/` |
| `npm run preview` | Serve the production build locally |
| `npm run lint` | ESLint |
| `npx playwright install chromium` | One-time: the browser for the end-to-end tests |
| `npm run test:e2e` | Browser tests (`e2e/`, 33 tests, ~12 min; one reads a scanned PDF with OCR when the backend has it) against the running backend (:8000) and dev server (:5173). They create data, so re-seed afterwards (`python scripts/reset_demo.py --yes`, server stopped) |
| `E2E_SHOTS=<folder> npm run test:e2e` | Same, and save screenshots of the key screens |

### Docker

```bash
# Backend: listens on 8000; ENVIRONMENT=production requires SECRET_KEY
cd BE && docker build -t paperless-factory-api .
docker run -p 8000:8000 --env-file .env paperless-factory-api
# with PDF / image import (adds ~1 GB); keep the OCR models in a volume
docker build --build-arg WITH_OCR=true -t paperless-factory-api .
docker run -p 8000:8000 --env-file .env -v paddlex:/home/appuser/.paddlex paperless-factory-api

# Frontend: VITE_API_URL is baked in at build time
cd FE/harman-paperless-factoryFE-main
docker build --build-arg VITE_API_URL=https://api.paperlessfactory.pravisht.com -t paperless-factory-frontend .
docker run -p 8080:80 paperless-factory-frontend
```

`BE/setup.sh` and `BE/setup.ps1` wrap the Docker build/run for the backend. Note that `setup.ps1` still writes obsolete AI variables.

---

## Configuration reference (backend `.env`)

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | — | Full SQLAlchemy URL; overrides the `DATABASE_*` parts |
| `DATABASE_HOST` / `PORT` / `NAME` / `USER` / `PASSWORD` | `localhost` / `5432` / `paperless_factory` / `postgres` / — | PostgreSQL connection |
| `AUTHENTICATION_ENABLED` | `false` | **Set `true`** anywhere real users log in |
| `ENVIRONMENT` | `development` | `production` → Secure cookies, `SECRET_KEY` required |
| `SECRET_KEY` | random per process | Set a fixed value, or sessions die on restart |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Sign-in lifetime; e.g. `480` for a shift |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:8000,http://127.0.0.1:8000` | Must include the frontend origin |
| `APP_BASE_URL` | `http://127.0.0.1:8000` | Base for links in emails; set it to the frontend URL |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_USE_TLS` / `SMTP_FROM` | — / 587 / — / — / true / — | Leave `SMTP_HOST` empty to run without email |
| `NOTIFICATIONS_COPY_TO` | — | Cc every notification to one address |
| `DATA_FOLDER`, `STORAGE_FOLDER`, `STAGING_FOLDER`, `LOGS_FOLDER`, `BACKUP_FOLDER` | `./data/...` | Written into the DB settings table on first boot; later `.env` changes to these have no effect |
| `DOCUMENT_MANAGER_HOST` / `DOCUMENT_MANAGER_PORT` | `127.0.0.1` / `8000` | Used by `cli.py serve` and `run.sh` |
| `DOC_FORMATS` | `pdf,image,excel` (`excel` without the OCR extra) | Document formats the template import accepts |
| `OCR_DET_MODEL` / `OCR_REC_MODEL` | `PP-OCRv5_mobile_det` / `en_PP-OCRv5_mobile_rec` | `PP-OCRv5_server_det` reads more accurately, ~3x slower on a CPU |
| `OCR_DEVICE` / `OCR_MKLDNN` | `cpu` / `1` | `gpu:0` needs `paddlepaddle-gpu`; `0` turns oneDNN off |

Settings are applied in this order, each overriding the one before: code defaults, then `config/models.json`, then `.env`, then the database `settings` table.

Frontend variables (`FE/.../.env*`):

- `VITE_API_URL` (or `VITE_BASE_URL`) is the backend origin.
- In dev it is used only as the proxy target, and the browser calls `/api/*` on :5173.
- In production builds it is the absolute API base URL.

## Where files are stored (backend)

| What | Path |
|---|---|
| Uploaded scans / evidence | `data/storage/evidence/YYYY-MM-DD/` |
| Generated record PDFs | `data/storage/evidence/generated/` |
| Blank format files | `data/storage/formats/<format_id>/` |
| Record attachments | `data/storage/records/<record_id>/attachments/` |
| Logs / backups | `data/logs/`, `data/backups/` |

The date-wise and month-wise filing folders are **logical folders in the database**, built from each format's frequency. They are browsed in the Doc Repository (`/api/documents/repository`).

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Browser shows a CORS error | Add the FE origin to `CORS_ORIGINS`. A **429 rate-limit** response also looks like a CORS error, because the limiter answers before CORS headers are added |
| 404 / 405 on a correct-looking URL | Trailing slash: `/api/roles`, `/api/departments` and `/api/my-approvals` must have **no** slash; `/api/settings/` and `/api/health/` **need** one (see INTEGRATION_PLAN.md §9.1) |
| Logged out too often | Raise `ACCESS_TOKEN_EXPIRE_MINUTES` (e.g. 480) and restart the backend |
| Approver cannot approve after restart | Authority comes from the user's role (plan B1). Assign a role with *Approval*, or re-run the seed for the demo users |
| Cookie not set on localhost | `ENVIRONMENT=production` makes it `Secure`; use `development` locally |
| Every action happens as "admin" | `AUTHENTICATION_ENABLED=false`; set it to `true` |
| Format won't release ("readiness") | The designer lists what is missing: the form must record something, and anyone named (PO / OPO / CFT / QMS) must be active and able to sign. Roles may be left blank; they are then chosen when each record is submitted |
| A Table / Grid records nothing | In Field Properties → Table layout, make at least one cell an input (text, number, date, ✓ / ✗). A number cell takes Min / Max / Unit |
| Upload File offers Excel only | The OCR extra is not installed: `pip install -r requirements-ocr.txt` and restart. `GET /api/ocr/formats` says why |
| A scan takes long to convert | OCR runs on the CPU: ~10 s an A4 page, 20–40 s a dense A3 check sheet. The first scan after a restart also loads the models. Excel is read in under a second |
| Emails not arriving | Without `SMTP_HOST` they are recorded as `skipped`; check `GET /api/records/notifications/outbox` (admin) |

## The process in the app

| Process step | Who | Screen |
|---|---|---|
| Blank formats on the server | Administrator | **Template Builder** → **New Template** (draw the form) or **Upload File** (an Excel sheet, PDF or scan of the paper form is read into fields) → **Edit**: title, code, team, library folder → **Continue**: responsibilities → **Send for approval**. The reviewer approves under **My Approvals → Template approvals**. The released format appears in **Resources** |
| Call a format and fill it | Process Owner | **Resources** → select → **File**. The fill page checks every reading against its limits as you type (OK / N-OK) and saves automatically; scans and photos can be attached |
| Submit for approval (emails the PO) | Process Owner | **Set up Approval**: confirm or choose the approvers → **Start Approval**. N-OK readings flag the Overall Process Owner |
| PO / OPO approval | PO, OPO | **My Approvals** → review page → **Approve** (signed) or **Return for correction**. The OPO can **Clear N-OK flag** |
| Quality CFT joint review | CFT members | Review page → **Agree** / **Object** (every member answers by the target date) |
| Final decision; "No" loops back to CFT | Process Owner | Review page → **Approve** (signed) or **Send back to CFT** (the record turns red) |
| File in date / month folders | Overall Process Owner | Review page → **File record** → **Doc Repository** (Records / team / format / year / month / day) |
| Change a format, or a new format | Anyone → QMS Coordinator | **Change Request** → Format changes → raise → the coordinator approves → **Create the new revision**, which opens in the designer and goes through the same release review |
| Tracking colours | Everyone | **My Documents** (colour column), **Track status**, review page: 🟢 OK for final review · 🟡 filling / in approval · 🔴 N-OK flag, CFT objection, overdue or sent back |

Also: **Dashboard** (KPIs, activity chart, what is waiting for you), **Notifications** (bell; every process trigger, emailed or not), **Activity Log** (audit trail), **Roles & Permissions** (people, teams, roles, departments; admins), **Settings** (profile, password).

## The template designer and document import

**Template Builder** lists templates by **Pending Approval**, **Change Request** and **Draft**. There are two ways to start a template:

- **New Template** opens *Document create*, the page the form is drawn on:
  - **Add Fields**: click a tile or drag it onto the page (basic, layout and advanced fields).
  - **Field Properties**: the selected field's label, key, placeholder, Required switch, options, default value, validation and width. A number field's **specification limits** and a choice's **conforming value** decide OK / N-OK when the record is filled.
  - **Table / Grid**: heading rows, merged cells, printed text and input cells (text, number, date, ✓ / ✗). A number cell takes its own Min / Max / Unit; a ✓ / ✗ cell is OK / N-OK.
  - The text toolbar formats a Header / Label / Paragraph (select text in its content box), aligns fields, zooms the page, and undoes / redoes.
  - **Edit** (Create Template): title, code (suggested when left blank), quality team and the **Resources library folder**; the folder is also where approved records are filed.
  - **Save Draft**, the eye (preview), and **Continue**: responsibilities (PO, OPO, CFT, QMS, frequency, work instruction), the blank form, **Send for approval**.
- **Upload File** reads a paper form into a template:
  - **Excel** (`.xlsx`, `.xlsm`, `.xls`) is read directly: boxes, shading, unlocked cells, drop-down lists, tick boxes and merged headings become fields, in under a second.
  - **PDF / image** (`.pdf`, `.png`, `.jpg`) is rendered, straightened and read with PaddleOCR: ruled tables, tick boxes and `Label: ____` lines become fields. The page is shown with what was found outlined before it opens in the designer, and a PDF or picture is kept as the template's blank form.
  - Every detected element can be changed in the designer before the template is released.

The backend side is `BE/app/ocr` (one handler per format behind a registry, and a shared grid interpreter), served under `/api/ocr/*`. Turning a document into a template needs template-management rights. The designer is built on the form builder in `FE/.../src/vendor/react-form-builder` (react-form-builder2 with a Table element and OCR views), kept as source so the designer can extend it.

## Deploying

The frontend and backend deploy separately (`FE/.github/workflows/deploy.yaml`, `BE/.github/workflows/deploy.yaml`). Before the first production release:

1. **Backend server `.env`**:
   - `AUTHENTICATION_ENABLED=true`, `ENVIRONMENT=production`, a fixed `SECRET_KEY`;
   - `ACCESS_TOKEN_EXPIRE_MINUTES` (e.g. 480);
   - `CORS_ORIGINS=<the frontend's https origin>`;
   - `APP_BASE_URL=<the frontend URL>` (links in emails);
   - the `SMTP_*` settings.
2. **Rotate the JWT secret.** An admin token was committed in an earlier frontend version: delete the `jwt_secret_key` row from the `settings` table (it is regenerated) and change the admin password.
3. **Frontend build**: `VITE_API_URL` is set in `FE/.github/workflows/deploy.yaml` and baked in at build time.
4. **CI:** the backend workflow now runs `pytest` **and** a `postgres-e2e` job (seed → API → `validate_workflow.py` + `check_frontend_contract.py` on PostgreSQL 16) before deploying.
5. **Users:** create real accounts in **Roles & Permissions**. Give approvers a role with *Approval*, and name them on each format.

## Project status

**Integration complete.** Every screen runs on the backend API, and the whole record process works end to end in the UI. Verified with:
- `pytest` (backend, 214 tests);
- `validate_workflow.py` (106 checks);
- `check_frontend_contract.py` (144 checks, through the Vite proxy and directly);
- Playwright browser tests (31, every screen and every process path, through the real UI).

The frontend type-checks, lints with 0 findings and builds without warnings.

Details of every phase and the fixes made along the way are in [INTEGRATION_PLAN.md §11](INTEGRATION_PLAN.md#11-progress-log). What remains (product decision D11 on approver permissions, email-link approvals, scheduled reminders) is listed in [§12](INTEGRATION_PLAN.md#12-open-items-after-integration).
