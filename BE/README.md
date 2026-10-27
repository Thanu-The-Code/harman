<div align="center">
  <h1>Quality Records</h1>
  <p><strong>Fill, approve, sign and file a quality record — the process the plant already runs, on a server.</strong></p>
  <p>
    <img src="https://img.shields.io/badge/Backend-FastAPI-4338CA?style=flat-square" alt="FastAPI">
    <img src="https://img.shields.io/badge/UI-Zero%20dependency-4338CA?style=flat-square" alt="UI">
    <img src="https://img.shields.io/badge/Backend-API%20only-4338CA?style=flat-square" alt="API only">
    <img src="https://img.shields.io/badge/License-MIT-6B7280?style=flat-square" alt="MIT">
  </p>
</div>

---

## About

A self-hosted system for the quality records a plant fills on paper today.

It implements one process, box by box: the client's *Record Filling & Record
Approval Process Flow*. Blank **formats** are held on the server with the
frequency they are filled at and the specification each reading must meet. A
record is filled on screen, or filled on paper and photographed — PaddleOCR
reads the sheet, keeps its table structure, and matches each reading back to the
field it belongs to. It is then routed through four signatures in a fixed order,
given a traffic-light status, and filed into date- or month-wise folders built
from the format's own frequency.

Three things are deliberate:

- **Nothing leaves the building.** Every OCR engine runs on this machine. There
  is no language model, no embedding service, no vector store and no API key —
  a plant that will not send its inspection sheets to a third party can still
  have them read.
- **Nothing is decided by the computer.** OCR produces *suggestions*; a person
  confirms every reading before it is written to a record.
- **The process is enforced, not recorded.** A step assigned to one person
  cannot be signed by another, including by an administrator; a record carrying
  an open out-of-specification flag cannot be filed; and a live format can only
  be changed through an approved change request.

## The record process

The system's primary job is the **record filling and record approval process**:
the controlled quality records a manufacturing quality team fills at a set
frequency, on formats held on the server. The navigation *is* that process — the
six screens are the six stages, in the order they happen.

```
 1. Formats → 2. Fill Record → 3. Approvals → 4. Tracking → 5. Storage → 6. Change Request
    blank        call one and    PO, Overall    green /       date- and     alter a format
    formats,     fill it, or     PO, CFT        yellow /      month-wise    only with QMS
    with their   scan the        joint          red           folders by    Coordinator
    frequency    paper copy      review,                      frequency     approval
    and specs    through OCR     final decision
```

**Four responsibilities**, named once on each format and applied to every record
raised against it, so nobody ever builds an approval chain by hand:

| Role | Does |
|---|---|
| **Process Owner** | Calls the format, fills the record, approves it if it is within specification, takes the final decision |
| **Overall Process Owner** | Approves after the Process Owner, receives N-ok flags, files the approved record on the server |
| **Quality CFT** | Joint review against a target date — *every* member must agree |
| **QMS Coordinator** | Approves every change to a format before it is executed |

Three things about it are worth stating plainly, because they are the parts a
generic approval tool gets wrong:

- **ok / N-ok is arithmetic, not opinion.** Each reading carries the
  specification it must meet, so the verdict is decided before anyone is asked
  to approve. Any out-of-specification reading raises a flag to the Overall
  Process Owner *immediately* — a flag that waits its turn in a queue is not a
  flag — and the record cannot be filed until the action taken is recorded.
- **A quality record is never rejected.** The chart has one decision point and
  no exit that discards a record, so every disagreement keeps it alive: a CFT
  member records an **objection** that the final decision has to weigh; a
  Process Owner who finds a record out of specification **returns it for
  correction**, unlocking the readings so the same record can be resubmitted;
  and a final decision that is not to approve sends it **back to the CFT** to
  be re-verified, turning it red. Records are only ever finished by being
  filed. The approval engine refuses to reject a record step at all, so there
  is no way in that loses one.
- **An active format cannot be edited.** Changing one requires a change request
  the QMS Coordinator approves, which then supersedes it with a new revision.
  A record keeps the revision it was filled against, for good.
- **Revisions stay in one format history.** Non-admin users see only the
  currently released revision; administrators can inspect every revision and
  its history. A change request must target the active released revision.
  The admin JSON endpoint `GET /api/formats/repository` returns one row per
  template, with its latest revision's ID and summary. Opening that ID through
  `GET /api/formats/{format_id}` returns the full details for the selected
  revision and, for administrators, every revision's full details in the
  `versions` array.
  `GET /api/formats/folders` returns the hierarchical Template Repo folder tree;
  template creators can add a folder with `POST /api/formats/folders` using a
  `name` and optional `parent_path`. Pass the selected folder's `path` as
  `storage_path` when creating a template. The Template Repo response includes
  the same folder hierarchy and groups released templates under their selected
  folder.
  Administrators may publish a ready draft without review through
  `POST /api/formats/{format_id}/publish-without-approval`; this bypass is
  blocked while a review is pending and recorded in the audit log.
  `GET /api/formats/{format_id}/approval` returns the latest approval status
  and reviewer comments; `GET /api/formats/{format_id}/approval/history`
  returns every review round, including rejected rounds and their comments.

Every record's status is one of the three the process defines:

| | |
|---|---|
| 🟢 **Green** | Ok for final review |
| 🟡 **Yellow** | Filling in progress |
| 🔴 **Red** | Needs to reverify with CFT — sent back, flagged N-ok, or past its target date |

Notifications fire at six points (record submitted, Process Owner approved,
N-ok flagged, CFT review opened, sent back for re-verification, change request
raised). Each is written to the database **before** any attempt to send, so the
trail is complete and auditable whether or not a mail server is configured —
see `SMTP_*` in `.env.example`.

## API domains

The FastAPI application is titled **Paperless Factory**. Its routers are
registered in `app/routers/api.py` and grouped under the following OpenAPI
titles in `/docs`:

| OpenAPI title | Router module(s) | Main API prefixes | Responsibility |
|---|---|---|---|
| **Identity & Access** | `auth.py`, `roles.py` | `/api/auth`, `/api/roles` | Sign-in, sessions, roles, and permission assignments |
| **People & Teams** | `auth.py`, `departments.py`, `formats.py` | `/api/auth/users`, `/api/departments`, `/api/formats/teams` | Manage people, departments, and teams |
| **Template Management** | `formats.py`, `change_requests.py` | `/api/formats`, `/api/change-requests` | Create, review, publish, and revise reusable templates |
| **Document Management** | `records.py`, `record_change_requests.py`, `documents.py` | `/api/records`, `/api/record-change-requests`, `/api/documents` | Fill records, request/approve/track record amendments, and manage document files |
| **Approval Workflows** | `workflow.py`, `signatures.py`, `approve.py` | `/api/workflow`, `/api/signatures`, `/api/approve` | Route documents through reviews, decisions, and signatures |
| **Corrective Actions** | `actions.py` | `/api/actions` | Track and close follow-up actions |
| **Audit Trail** | `audit.py` | `/api/audit` | Inspect recorded activity with date-range, module, search, action, and paginated filters; `/api/audit/modules` lists module filter values |
| **Platform Administration** | `settings.py`, `admin.py` | `/api/settings`, `/api/admin` | Configure and administer the application |
| **Backup & Recovery** | `backup.py` | `/api/backup` | Create and restore backups |
| **Platform Health** | `health.py` | `/api/health` | Check service health and readiness |
| **Security** | `security.py` | `/api/security` | Review and manage security controls |

People & Teams operations are exposed by routes in the identity and template
routers; they do not have a separate router module. These are modular domains
within one FastAPI deployment, not separately deployed microservices. The
documented prefixes are the router mounts in `app/routers/api.py`; the OpenAPI
titles group their operations in `/docs` without changing client URLs.

Administrators can create departments with `POST /api/departments` and load
them for a user-creation selector with `GET /api/departments`. Pass the chosen
department's `id` as `department_id` to `POST /api/auth/users`; the user's
existing `department` field is also populated with the department name for
workflow compatibility. An unused department can be deleted with
`DELETE /api/departments/{department_id}`; reassign or remove its users first.

### Role and permission management

Administrators can manage custom roles through `/api/roles`. The role editor
uses four business-level capabilities instead of exposing internal API
permission keys:

| Capability | Grants |
|---|---|
| `documents.view` | View documents and released templates |
| `records.fill` | Create/fill records and submit them for approval |
| `templates.create` | Create/edit draft templates and submit them for approval |
| `approvals.approve` | Approval |

The API expands these capabilities to the internal checks used by each route.
The UI label for `approvals.approve` is simply **Approval**; internally it
grants both the approve and sign permission required to complete assigned
approval steps. Workflow assignee checks still decide which steps that person
may act on.

For template approval, `GET /api/formats/approvers` returns active users with
approval permission for a multi-select picker; pass `role_id` to limit the list
to users assigned to that role. `POST /api/formats` saves the form details and
designer fields/layout as a draft; its Swagger request schema does not include
reviewers or role assignments. When the user continues to the approval screen,
call `POST /api/formats/{format_id}/submit-approval` with ordered steps
containing `role_id`, the selected `reviewer_ids`, and `mode`. Every reviewer in
an `all` step must approve before that step completes. A submission can also
include an overall `priority` (`low`, `normal`, `high`, or `urgent`) and an
optional `due_days` value (1-365) on each step. These are stored as approval
metadata; they do not schedule reminders or enforce deadlines. Approvers can get their
assigned pending forms, including each `format_id`, from
`GET /api/formats/approvals/mine`; they do not need the form ID in advance.
`GET /api/formats/{format_id}` returns template details and its latest approval
round together in the `approval` property. For a draft with no submitted review,
that property has `status: "none"` and no steps; while pending or after rejection,
it includes step reviewers, decisions, and comments. The separate
`GET /api/formats/{format_id}/approval` endpoint remains available.

The Template Builder landing screen can use `GET /api/formats?tab=all` to get
all unpublished current template revisions and their counters. Supported tabs
are `on_verification`, `change_request`, `draft`, and `all`; `q` searches code
or title. The response always includes global counters and returns the selected
tab's rows in `formats`. Total unpublished templates is the sum of Draft,
On Verification, and Change Request; published templates are excluded.
Change Request rows are drafts whose latest template approval was rejected.
`GET /api/formats/stats` remains available for counts only.

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/roles/permissions` | List permission keys accepted by the API |
| `GET` | `/api/roles` | List roles and their permission keys (`assignable` marks custom roles) |
| `POST` | `/api/roles` | Create a role with a name, description, and permission keys |
| `GET` | `/api/roles/{role_id}` | Get one role |
| `PUT` | `/api/roles/{role_id}` | Update a custom role |
| `DELETE` | `/api/roles/{role_id}` | Delete an unassigned custom role |
| `PUT` | `/api/roles/users/{user_id}` | Set the user's role (`{"role_id": "..."}`) |

Create users with `username`, `email`, `full_name`, `password`, and the selected
`role_id` in `POST /api/auth/users` (the password: at least 8 characters, mixing
three of lower case, upper case, digits and symbols; usernames are letters,
digits, `.`, `-`, `_`). Signing out, changing or resetting a password, and
deactivating an account end that person's existing sign-ins, or assign/replace their role later with the
endpoint above. User creation requires a role selection; that role supplies the user's
permissions. On startup, the application removes
the old seeded roles and clears their assignments while retaining
administrator-created roles. Existing built-in role names remain reserved.
An assigned custom role must be removed from its users before it can be deleted.
Record amendment requests are distinct from `/api/change-requests`, which
controls revisions to reusable formats. `/api/record-change-requests` lists
requests with status counts, text/department filters and pagination; it also
supports request detail, editing while open, assignment, approval/rejection,
and marking an approved request implemented. Detail responses include the
linked record's filled-by/date, department, document, and completed-item
summary.

## The evidence

A record's evidence is the scanned sheet it was filled from. It is stored, read
once, and afterwards only looked at — so there is no repository around it: no
folders, no tags, no correspondents, no versioning. A sheet may be the evidence
for exactly one record, and the system refuses a hard copy it has already filed,
so nobody can quietly reuse one.

**Built with** FastAPI · SQLAlchemy · PostgreSQL ·
PaddleOCR with a geometric table recovery, Tesseract behind it · and a front end
of plain HTML, CSS and JavaScript with no build step.

> **Full technical documentation** — architecture, data model, API reference,
> security design and operations runbooks — is in
> **[docs/DMS-Project-Documentation.md](docs/DMS-Project-Documentation.md)**,
> also split by chapter under [docs/srs/](docs/srs/README.md).

---

## Quick start

Five minutes from a clone to a working system with a worked example in it.

### 1 · Install

**Requirements:** Python 3.12 · Node 20+ (for the form builder) · Tesseract OCR
and Poppler (for reading scans) · 4 GB RAM · 10 GB free disk.

<details open>
<summary><strong>Windows</strong></summary>

```powershell
winget install UB-Mannheim.TesseractOCR
choco install poppler

python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pip install python-magic-bin==0.4.14   # libmagic DLLs, Windows only

copy .env.example .env
```

Then set `TESSERACT_PATH` and `POPPLER_PATH` in `.env` to wherever those two
installed.

> On Windows, `python-magic` needs a libmagic binary. If a scan upload exits
> without an error, install the bundled build:
> ```powershell
> .venv\Scripts\pip install python-magic-bin==0.4.14
> ```
</details>

<details>
<summary><strong>Linux</strong></summary>

```bash
sudo apt-get install -y tesseract-ocr poppler-utils libmagic1

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env
```
</details>

<details>
<summary><strong>Docker</strong></summary>

```bash
./setup.sh build
./setup.sh prod
```

`setup.sh` drives Docker or Podman only. Use `run.sh` or `cli.py serve` to start
the application directly.
</details>

> Starting **without** the demo data instead? Run `python cli.py init` then
> `python cli.py serve`, and the first account you create through the sign-in
> page becomes the administrator.

Set a real `SECRET_KEY` in `.env` before this reaches a network. Everything else
has a working default, and **the AI provider is optional** — the system runs with
no API key and the AI features switched off.

### 2 · Build the form builder

The template designer and the form renderer on the fill screen are a small
React application under `form-builder-free/`. Its build output is deliberately
not committed, so a fresh checkout has to build it once:

```bash
cd form-builder-free
npm install
npm run build                # writes form-builder-free/dist
cd ..
```

**Requires Node 20.19 or later** (Vite 8). On Windows: `winget install OpenJS.NodeJS.LTS`.

Skip this and the application still starts, but *New template* and *Edit* in
the Doc Builder answer `Form Builder build not found`, and the fill screen
falls back to its plain renderer because `/form-builder/assets/fill-main.js` is
not there. Rebuild after any change under `form-builder-free/src`.

The Docker image builds it itself, in its own Node stage, so this step is only
for running from a checkout.

### 3 · Create the database

```bash
python cli.py init          # tables, folders, quality teams, default settings
```

`python cli.py serve` also creates or migrates the database schema before
loading database-backed settings, so it can start against a new empty database.
Run `init` once as well when you want the complete folder and team setup.

### 4 · Load the worked example

```bash
python scripts/seed_quality_records.py
python cli.py serve         # then open http://127.0.0.1:8000
```

The seed creates the administrator too if the database is empty, so those three
commands take you from nothing to a running system with a worked example in it.
(On a system that already has an administrator it leaves them alone.)

It creates the **three quality teams**, the **seven people the process names**,
**three released formats** at three different frequencies, and five records left
in deliberately different states — one filed, one carrying an open N-ok flag, one
sent back to the CFT, one still being filled, and one change request waiting on
the QMS Coordinator. It is idempotent, so running it twice changes nothing.

Everyone it creates shares one demo password. It is not published here: ask the
project administrator for it, and give every account its own password with
`python cli.py reset-password NAME` before real people use the system.

| Sign in as | Their part in the process |
|---|---|
| `admin` | Administrator — builds and releases formats |
| `r.kumar` | **Process Owner** (Process Quality) — calls, fills, approves, decides |
| `s.iyer` | **Overall Process Owner** — second approval, N-ok flags, files records |
| `a.deshmukh` | **Quality CFT** |
| `p.nair` | **Quality CFT** |
| `m.shaikh` | **QMS Coordinator** — approves format changes |
| `k.reddy` | **Process Owner** (Supplier Quality) |

> Change these passwords before the system reaches a real network.

---

## Every command

```bash
# Getting going
python cli.py init                      # create the database, folders and teams
python cli.py serve                     # start the server on 127.0.0.1:8000
python cli.py status                    # folders, counts, OCR

# The record process
python cli.py records                   # the traffic light, and what is stuck
python cli.py ocr                       # which OCR engine reads scans, and what it recovers
python cli.py change-requests           # open change requests and who they wait on

# People
python cli.py users                     # list accounts
python cli.py reset-password NAME       # set a new password

# Documents
python cli.py process                   # process the staging folder now

python cli.py sync-model-config         # push config/models.json into the database

# Database and backups
python cli.py db analyze|optimize|create-indexes|size
python cli.py backup create|list|restore

# Demonstration data
python scripts/seed_quality_records.py  # three teams, three formats, worked examples
python scripts/make_sample_sheet.py     # two filled inspection sheets to scan
python scripts/reset_demo.py            # put it all back to a clean demo state

# Bringing older data in line (safe to run again; --dry-run lists what would change)
python scripts/convert_image_evidence.py  # hard copies stored as pictures -> PDF, so they carry signatures
python scripts/sync_format_fields.py      # template fields in reading order; table cells required only when marked
```

`make_sample_sheet.py` writes `harman-inspection-sheet.pdf` and
`harman-inspection-sheet-nok.pdf` into the project root — a filled QF-PQ-001
with every reading in specification, and the same sheet with the bore diameter
out of specification so the N-ok route (**B5**) can be shown. Both are
image-only, with no text layer, so attaching one genuinely exercises the OCR.

`reset_demo.py` is the way back to a known state after a demonstration or a test
run: it wipes the database and the filed evidence, re-seeds, and stamps a fresh
pair of sheets. A scanned sheet may only ever be the evidence for one record, so
after a demo the sheets are spent - this makes them attachable again. Stop the
server first; the script refuses to run while it is up.

`run.sh` is the Linux equivalent of `cli.py serve` and passes extra arguments
through to uvicorn:

```bash
DOCUMENT_MANAGER_PORT=8080 ./run.sh     # a different port
DOCUMENT_MANAGER_HOST=0.0.0.0 ./run.sh  # reachable from other machines
./run.sh --reload                       # auto-reload while editing
```

Binding to `0.0.0.0` also needs that origin added to `CORS_ORIGINS` in `.env`.

Interactive API documentation is at `/docs` and `/redoc` once the server is
running in development. With `ENVIRONMENT=production` they (and `/openapi.json`)
are not served.

---

## Testing it

> **[TESTING.md](TESTING.md)** is the practical companion to this section:
> every command in order, and a box-by-box manual walkthrough of the flowchart
> with what to look for at each step.
>
> **[DEMO.md](DEMO.md)** is the screen-by-screen script for showing the system
> to somebody who has not seen it — which menu item to open, in what order, what
> to say at each one, and which box of the flowchart it covers.


Two layers, and they answer different questions.

### The test suite — "is the code correct?"

```bash
python -m pytest tests/ -q                        # everything, about 6 minutes
python -m pytest tests/test_qms_record_workflow.py -q   # the process rules
python -m pytest tests/test_qms_api.py -q               # the same rules over HTTP
```

Every test in those two files is named for the box of the flowchart it defends,
so a failure tells you which rule of the process has stopped holding.

### The acceptance check — "does the running system match the process?"

```bash
python cli.py serve                       # in one terminal
python scripts/validate_workflow.py       # in another
```

This signs in as each of the seven people and walks the whole flowchart against
a live server: every frequency filed to its own folder, the segregation of
duties, the ok/N-ok arithmetic, the N-ok flag, the joint review quorum, the
re-verification loop, change control, the notification triggers, two people
acting at the same moment, and whether the numbers on the screens reconcile.
It prints one line per business expectation and exits non-zero on any finding.

```bash
python scripts/validate_workflow.py --url http://127.0.0.1:8080   # elsewhere
python scripts/validate_workflow.py --quick                       # skip the slow parts
```

It creates its own formats under a `QV-` prefix so it never disturbs your data,
and it is safe to run repeatedly.

---

## Walking the process yourself

About twenty minutes in the web app (http://127.0.0.1:5173), with the seeded people
(password `Harman@2026`). Keep two browser profiles open to be two people at once.
Button and screen names below are exactly what the app shows.

### B1 · A template — as `admin`

1. **Template Builder → Upload File**: choose a sample (an Excel workbook, PDF or
   photo of a paper form) and press **Convert**. What was detected is shown over
   the page; press **Open in designer**.
2. **Create Template** asks for the title (suggested from the form), the quality
   team and the library folder. Leave **Form code** blank: the server gives the
   team's next code.
3. In the designer, click any element to edit it in **Field Properties** (label,
   Required, limits). A table opens in **Edit table**: make cells ✓ / ✗ or numbers,
   give a number limits (**Limits to row** copies them across the days).
4. **Save Draft**, then **Continue**: frequency, Process Owner, Overall Process
   Owner, QMS Coordinator, Quality CFT, work instruction. **Send for approval**.
5. As **`m.shaikh`**: **My Approvals → Template approvals → Review → Approve**.
   It is released into the **Resources Library** (or **Reject** with a comment: the
   author is told and it comes back as a draft).

### B2, B3 · Filling a record — as the Process Owner (`r.kumar`)

6. **Resources Library**: open the folder, select the template, press **File**.
7. Fill it in. A reading with limits shows **OK / N-OK** as you type; everything
   saves as you go. Optionally **Attach the scanned hard copy** (a PDF or photo of
   the paper sheet, kept as the record's document).
8. **Set up Approval** shows who approves (blank required entries are listed), then
   **Start Approval**.

### B4 … B8 · The approval chain — each person from **My Approvals**

9. **Process Owner** (`r.kumar`): **Approve** and sign — or **Return for correction**
   with a reason (the record comes back with the reason shown on it).
10. **Overall Process Owner** (`s.iyer`): if a reading was N-OK, **Clear N-OK flag**
    with the action taken; then **Approve** and sign.
11. **Quality CFT** (`p.nair`, `a.deshmukh`): each **Agree**s or **Object**s. The
    joint review closes only when both have answered.
12. **Final decision** (`r.kumar`): **Approve**, or **Send back to CFT** for
    re-verification (the record turns red until the CFT agrees again).
13. **Overall Process Owner**: **File record**. It goes into the **Doc Repository**
    under `Teams / <team> / <folder> / <template code> / <year> / <month> [/ <day>]`,
    with its readings, approval timeline, trail and the signed PDF (**Open**,
    **Download**).

### D2, B9 · Changes — `r.kumar`, then `m.shaikh`

14. A template change: **Change Request → New change request**, choose the
    template, say what and why. As **`m.shaikh`**: open it, **Start review**,
    **Approved**, then **Create the new revision**; an administrator opens the draft
    in the designer, changes it and sends it for approval. Once released, the old
    revision is superseded; records filed on it keep saying so.
15. A record change: on a filed record, **Request a change**; the QMS Coordinator
    decides it, and it is **Mark implemented** with what was done. It shows in the
    record's trail in the Doc Repository.

### Everyone

16. **Dashboard**: records, approvals waiting (overdue included), change requests,
    active templates, over the chosen range. The **bell** and **Notifications**
    open the screen each message is about. **Activity Log** lists what was done
    (administrators also see sign-ins).

---

## Demonstrating it to somebody new

Ten minutes, one screen. Sign in as `admin` first and have the seed loaded.

| # | Show them | Say |
|---|---|---|
| 1 | **Formats** | "Every blank format lives on the server with the frequency it is filled at, the limits each reading has to meet, and the four people who act on it. Nobody builds an approval chain by hand." |
| 2 | **Record Register**, press the red tile | "Three colours, exactly as the process defines them. Red is a record that needs to go back to the CFT. One click and here they are." |
| 3 | Sign in as `r.kumar` → **Fill Record** | "The menu *is* the process. This person is only offered the formats they own, for the period that is due." |
| 4 | Type an out-of-spec reading | "ok or N-ok is decided by arithmetic against the limit on the row, before anybody is asked to approve it." |
| 5 | **Attach the scanned hard copy** | "They can keep filling the paper form exactly as they do today. It is scanned, read by OCR, and the readings come across." |
| 6 | Sign in as `s.iyer` → **Tracking** | "An out-of-specification reading flags the Overall Process Owner the moment the record is submitted — it does not wait in the queue — and the record cannot be filed until the action taken is recorded." |
| 7 | Sign in as `a.deshmukh` → approve → back to **Tracking** | "The joint review is *joint*. One member agreeing does not conclude it." |
| 8 | As `r.kumar`, **Send back to the CFT** | "This is the part a generic approval tool gets wrong. Rejecting the final decision does not throw the record away — it goes back to the CFT, turns red, and every earlier CFT approval is cleared. Nothing is ever lost." |
| 9 | **Storage** | "Filed into date and month folders built from the format's frequency. No one maintains this tree." |
| 10 | As `m.shaikh` → **Change Request** | "And no format changes at all without the QMS Coordinator approving it first. The old revision is superseded, never deleted, and records keep the revision they were filled against." |

Finish with the acceptance check on screen — it is the most convincing thing in
the repository:

```bash
python scripts/validate_workflow.py
```

It walks the whole flowchart against the running system as all seven people and
prints one line per business rule.

---

## Reading scanned paper

The client fills these formats on paper today, so how well a photograph of a
filled sheet is read is not a detail — it is the difference between
digitisation and retyping.

**PaddleOCR replaces Tesseract as the accurate engine, and the document keeps
its shape.** PP-OCRv5 reports every recognised line *with its position*, and a
quality record is a ruled grid — so the table is read back out of that geometry:
lines sharing a horizontal band are a row, text sharing a vertical band is a
column. A scanned format still looks like the format afterwards, instead of
becoming a wall of words in which nobody can tell which column a number came
from.

That structure earns its keep immediately. When a Process Owner attaches a
photographed sheet, the recovered table is matched against the format's own
field labels and the readings are **offered back as suggestions** — they confirm
them instead of retyping a form they have already filled once on paper.

Measured on a 1240×900 inspection sheet, reading it cold:

| | |
|---|---|
| Readings correctly extracted | **5 of 5** |
| Recognition confidence | **96%** |
| Time to read the page | **4.6 s** |
| Engine ready (once per process, at startup) | 24 s |

Two of those five are the ones that matter: the bore diameter came back as
`25.02`, not the `24.90` sitting in the specification column beside it, and the
surface finish as `0.84`, not the `1.6` in `max 1.6`. A specification read as a
measurement is always plausible and always in specification, so nobody notices
it is wrong — the matcher steps over any cell that names a limit, states a
range, or equals one of the field's own bounds.

> **Suggestions, never facts.** Nothing is written to a record until a person
> has looked at it. An engine that reads 25.02 as 26.02 must not be able to put
> an out-of-specification reading into a quality record on its own — the whole
> point of B4 is that somebody confirms it. The panel shows what each value
> would mean, including **"would be N-ok"**, before it is accepted.

### Installing it

PaddleOCR is optional and kept out of `requirements.txt` because it is large —
roughly 700 MB installed, plus models downloaded on first use and cached in
`~/.paddlex`.

```bash
pip install -r requirements-ocr.txt
python cli.py ocr          # confirm which engine will read a scan
```

Without it the chain falls through to Tesseract. Nothing breaks; the tables are
simply lost, and with them the ability to match a reading to its own field.

The engine is built **lazily, in the request thread that first needs it** — not
at startup. Constructing Paddle's predictors inside a startup executor hangs
under uvicorn: the server stays healthy and the thread never returns, so nothing
looks wrong until somebody scans a sheet. The cost is about 25 seconds on the
first scan after a restart, and nothing on every scan after it.

### The engine chain

Set `ocr.engine` in [`config/models.json`](config/models.json), or `OCR_ENGINE`
in `.env`:

| `ocr.engine` | What runs |
|---|---|
| `auto` *(default)* | A PDF's own text layer → **PaddleOCR** → Tesseract |
| `paddle` | Force PaddleOCR; Tesseract only as a last resort |
| `tesseract` | Classic local OCR only; PaddleOCR is never called |

Every one of them runs on this machine. PaddleOCR comes first because it is
deterministic and structure-aware: it is the only engine here that returns the
document's *layout*, so a scanned quality format still looks like the format
and its readings can be matched back to the fields they belong to.

### Options

Under `ocr.paddle` in `config/models.json`:

| Setting | Default | What it does |
|---|---|---|
| `models` | `mobile` | `mobile` or `server`. The server pair is more accurate on a difficult scan and **about fifty times slower on a CPU** — 225 s for the sheet above, against 4.6 s. Use `server` with a GPU. |
| `table_recognition` | `true` | Recover each table from where the words sit. Costs nothing; the detector already gave us the boxes. |
| `table_model` | `false` | Use PaddleOCR's own cell-detection pipeline instead. More accurate on a wildly irregular table; it took **over ten minutes for one page** on a CPU here. GPU only. |
| `correct_orientation` | `true` | Straighten a sheet that went into the scanner upside down. Cheap. |
| `flatten_curled_pages` | `false` | Unwarp a curled page. Aimed at photographs of bound books; the heaviest model in the pipeline. |
| `detection_side_length` | `960` | How far the longer side is scaled before detection. Raising it finds smaller print at roughly quadratic cost. |
| `dpi` | `300` | Scanned PDFs are rasterised at this. 300 reads small print and thin table rules far better than the 200 Tesseract wanted. |
| `use_gpu` | `false` | With an NVIDIA card, install `paddlepaddle-gpu` and set this. |

---

## Configuration

Copy `.env.example` to `.env`, set a strong `SECRET_KEY`, and set `DATABASE_PASSWORD` to the password for your local PostgreSQL `postgres` role. Use `DATABASE_URL` only when you want to provide the complete connection string; it takes precedence over the individual `DATABASE_*` values.

Sign-in is required by default: with no `.env`, or `AUTHENTICATION_ENABLED` unset,
the server fails closed. For local API testing only, `AUTHENTICATION_ENABLED=false` allows API requests without
a Bearer token or login session. Requests run with the active administrator's
permissions when one exists; otherwise the app uses an ephemeral administrator
identity, so a fresh database works without creating a user first. Anonymous
operations have no user ID for audit or ownership attribution. This grants
unrestricted access: keep the server bound to localhost and set
`AUTHENTICATION_ENABLED=true` before exposing it to other machines or networks.

```dotenv
SECRET_KEY=replace-with-a-generated-value
ENVIRONMENT=production
AUTHENTICATION_ENABLED=true

DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=paperless_factory
DATABASE_USER=postgres
DATABASE_PASSWORD=your-postgres-password
# Alternatively, set DATABASE_URL instead of these DATABASE_* values.
# DATABASE_URL=postgresql+psycopg://postgres:your-postgres-password@localhost:5432/paperless_factory

# OCR: auto (a PDF's text layer, then PaddleOCR, then Tesseract) | paddle | tesseract
OCR_ENGINE=auto

# Where the OCR tools are installed
TESSERACT_PATH=/usr/bin/tesseract
POPPLER_PATH=/usr/bin

# Mail, for the six trigger notifications the process asks for.
# Leave SMTP_HOST empty to run without email - notifications are still
# recorded, and marked "skipped" rather than "failed".
SMTP_HOST=
APP_BASE_URL=http://127.0.0.1:8000
```

**How a sheet is read is not set here.** It lives in
[`config/models.json`](config/models.json). Settings resolve in this order,
lowest priority first:

```
code defaults  →  config/models.json  →  environment / .env  →  database
```

The database wins, so a value saved through the Settings screen overrides `.env`.
Run `python cli.py sync-model-config` to push `config/models.json` back over
stale database rows.

---

## Seeded API smoke check

Run the standalone integration check from the repository root:

```powershell
.\.venv\Scripts\python.exe scripts\seed_and_test_api.py
```

It creates a temporary SQLite database, inserts representative typed sample
rows into every table registered by the application, then checks the seeded
document metadata, preview-info, OCR-text, file, and download API responses.
The temporary database and evidence file are removed when the check finishes;
the configured development or production database is not used. The sample data
covers column types and populated relationships with representative values; it
does not enumerate every status/choice or unbounded text value.

---

## License

MIT. See [LICENSE](LICENSE).

This is a derivative of the open-source
[`JayRHa/DocumentManager`](https://github.com/JayRHa/DocumentManager) project,
original work © Jannik Reinhard and Fabian Peschke, MIT licensed. All upstream
copyright notices are retained.
