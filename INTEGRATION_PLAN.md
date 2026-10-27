# Paperless Factory — Frontend ↔ Backend Integration Plan

| | |
|---|---|
| **Status** | ✅ **Integration complete — Phases 0–9 done** (see [§11 Progress log](#11-progress-log)). Open items are listed in [§12](#12-open-items-after-integration) |
| **Date** | 2026-10-22 (plan) · 2026-10-23 (completed) |
| **Scope** | Wire every built backend API into the React frontend so the full *Record Filling & Record Approval* process (see `Project Core Workflow.pdf`) runs end to end |
| **Repos** | `BE/` (FastAPI) · `FE/harman-paperless-factoryFE-main/` (React + Vite) |
| **Owners legend** | **FE** frontend · **BE** backend · **QA** test · **PO** product decision |
| **Size legend** | **S** ≤ ½ day · **M** 1–2 days · **L** 3–5 days |

> How to use this document: read §1–§4 once for context. §5 is the screen-by-screen API map, the reference you keep open while coding. §6 is the ordered, step-by-step work plan; each step has tasks, files, and a "Done when" check. §8 lists the decisions the team must confirm **before** Phase 1 starts.

---

## Contents

1. [The business workflow and how the backend models it](#1-the-business-workflow-and-how-the-backend-models-it)
2. [Where we are today](#2-where-we-are-today)
3. [Integration architecture](#3-integration-architecture)
4. [Blockers found during the review](#4-blockers-found-during-the-review)
5. [Screen-by-screen API map](#5-screen-by-screen-api-map)
6. [Phased implementation plan](#6-phased-implementation-plan)
7. [End-to-end acceptance scenarios](#7-end-to-end-acceptance-scenarios)
8. [Decisions needed from the team](#8-decisions-needed-from-the-team)
9. [Reference: API conventions & gotchas](#9-reference-api-conventions--gotchas)
10. [Out of scope / later](#10-out-of-scope--later)
11. [Progress log](#11-progress-log)
12. [Open items after integration](#12-open-items-after-integration)

---

## 1. The business workflow and how the backend models it

### 1.1 Process (from `Project Core Workflow.pdf`)

```
Blank formats on server
  → Process Owner calls a format and fills the record per work instruction
  → (email) Process Owner approves if within spec
  → (email) Overall Process Owner approves
  → Record stored with status OK / N-OK  ── N-OK raises a flag to Overall Process Owner
  → Quality CFT joint review, with a target date
  → Final decision ── reject → back to CFT re-verification (loop)
  → Approved record filed on server in date-wise / month-wise folders (by frequency)
  → Any change to an existing format / new format?
       → Document Change Request (DCR) → mail QMS Coordinator → QMS approves → triggers Process Owner
Tracking colours:  🟢 OK for final review · 🟡 filling in progress · 🔴 needs re-verify with CFT
```

### 1.2 Who is who

Workflow roles are **assigned per format**, not global RBAC roles. Each format names its Process Owner (PO), Overall Process Owner (OPO), QMS Coordinator and CFT members (`BE/app/models_qms.py` → `formats`, `format_cft_members`). RBAC roles (`/api/roles`) only grant broad capabilities: `documents.view`, `records.fill`, `templates.create`, `approvals.approve`.

### 1.3 Business step → backend implementation

| # | Business step | Backend (service / endpoint) | Record `stage` | RAG |
|---|---|---|---|---|
| 1 | Blank formats stored on server | `formats` table; layout + fields; blank file `POST /api/formats/{id}/blank`; release via review → `active` | — | — |
| 2 | PO calls the format | `POST /api/records/call` (`record_service.call_format`) | `filling` | 🟡 |
| 3 | Fill per work instruction; live spec check | `PUT /api/records/{id}/values` → `in_spec`, `observation_status` ok/not_ok | `filling` | 🟡 |
| 4 | Email PO for approval | `POST /api/records/{id}/submit` → generates PDF, builds the QMS chain, emails `record.submitted` | `po_approval` | 🟡 |
| 5 | N-OK → flag to OPO | at submit: `inspection.failed` + `raise_nok_flag` (`record.nok_flagged`) | — | 🔴 |
| 6 | PO approves → email OPO | `POST /api/workflow/{wf}/steps/{step}/decide` → `record.po_approved` | `opo_approval` | 🟡 |
| 7 | OPO approves → CFT joint review with target date | same decide endpoint → `record.cft_review`; `cft_target_date` | `cft_review` | 🟢 / 🔴 if overdue |
| 8 | CFT members agree / object | `POST /api/records/{id}/cft-opinion` (all members must answer) | → `final_decision` | 🟢 / 🔴 on objection |
| 9 | Final decision; reject loops to CFT | decide (approve) / `POST /api/records/{id}/reverify` | `final_decision` / back to `cft_review` | 🔴 on re-verify |
| 10 | Store in date/month folders | `POST /api/records/{id}/store` (OPO) → folder chain by frequency | `stored` | 🟢 |
| 11 | Change to format → DCR → QMS Coordinator | `/api/change-requests` create → review → decide → execute (new revision/new format) | — | — |

PO/OPO "reject" or "changes" → `return_for_correction` → record goes back to `filling` and a fresh chain is built on resubmit.

**Conclusion:** the backend already implements the whole process. The integration work is mostly frontend, plus a short list of backend fixes (§4) that block a working end-to-end flow.

---

## 2. Where we are today

### 2.1 Backend (BE)

- FastAPI, ~95 endpoints under `/api/*` across 20 routers (`BE/app/routers/api.py`). Swagger at `http://127.0.0.1:8000/docs`.
- PostgreSQL by default; SQLite works for local dev and tests.
- Auth: JWT bearer (30 min) **and** an HttpOnly `session_token` cookie (24 h). **Auth is OFF by default** (`AUTHENTICATION_ENABLED=false`); in that mode every request runs as the first admin.
- Email over SMTP (optional). With no SMTP every notification is still stored and shown in-app with status `skipped`.
- OCR and Excel import live in `app/ocr/` behind `/api/ocr/*` (§13); the old `POST /api/formats/digitize` stub is removed.
- The unmounted `routers/format_approvals.py`, `format_blanks.py`, `format_library.py`, `format_teams.py`, `format_templates.py`, `format_api_schemas.py`, `format_api_serializers.py` are removed (§14).

### 2.2 Frontend (FE)

- React 19 + Vite 8 + TypeScript, MUI 9, Redux Toolkit 2, AG Grid, AG Charts, `react-form-builder2`, axios.
- **UI is essentially complete; data wiring is about 5%.** Most screens render from `src/constants/data.ts`, `src/docRepository/data.ts` and `src/templateBuilder/data.ts`.

| Screen (route) | Component | Data source today |
|---|---|---|
| Login `/login` | `login/index.tsx` | ✅ `POST api/auth/login` — but the token is **never stored** |
| Dashboard `/` | `dashboard/DashboardPage.tsx` | ❌ hard-coded constants |
| Resources Library `/resources` | `resources/ResourceDashboad.tsx` | ⚠️ `GET api/formats/`; "Create Folder" **creates a junk placeholder format** |
| My Documents `/my-forms` | `myForms/MyFormsDash.tsx` | ❌ `templateRows` mock |
| Form fill `/my-forms/:id`, `/resources/file` | `myForms/FormDetails.tsx` | ❌ hard-coded fields + 31-day inspection table |
| Set up approval `/my-forms/:id/approval` | `myForms/ApprovalSetupPage.tsx` | ❌ `console.log` |
| Track status (`?tab=track`) | `myForms/TrackStatus.tsx` | ❌ mock |
| My Approvals `/my-approvals` | `myApprovals/index.tsx` | ❌ mock |
| Approval review `/my-approvals/:id` | `myApprovals/ApprovalReview.tsx` | ❌ mock; actions `console.log` |
| Template Builder `/builder` | `templateBuilder/index.tsx` | ⚠️ stats from `GET api/formats/stats`; grid mock |
| Template detail `/builder/:id` | `templateBuilder/BuilderTemplateDetail.tsx` | ❌ mock |
| Form designer `/builder/:id/build` | `templateBuilder/builder/index.tsx` | ✅ get/create/update format, teams; ⚠️ "Release" calls `/activate`, which fails without an approved review |
| Template Repo `/builder-repo` | `templateRepo/index.tsx` | ⚠️ `GET api/formats/repository`, but the mapper expects a different shape |
| Doc Repository `/doc-repo` | `docRepository/index.tsx` | ❌ mock |
| Change Request `/request`, `/change-request/:id` | `changeRequest/*` | ❌ mock |
| Roles & Permissions `/people-teams` | `peopleAndTeams/*` | ❌ mock; dialogs `console.log` |
| Activity Log `/activity-log` | `activityLog/index.tsx` | ❌ mock |
| Notifications popup + `/notifications` | `header/NotificationPopUp.tsx`, `NotificationsPage.tsx` | ❌ mock; badge hard-coded "3" |
| Settings `/settings` | `header/Settings.tsx` | ❌ local state only |
| Header user chip | `header/Header.tsx` | ❌ hard-coded "Admin / Super Admin" |

---

## 3. Integration architecture

### 3.1 Environments and how the FE reaches the BE

```
Local dev                         Production
Browser → Vite :5173              Browser → nginx (FE static)  https://<fe-domain>
   └─ /api/* proxied → BE :8000      └─ XHR (CORS) → https://api.paperlessfactory.pravisht.com
```

- **Dev:** `src/constants/index.ts` uses `base_url = "/"` in dev and `vite.config.ts` proxies `/api` to `VITE_API_URL`. Same-origin through the proxy, so there are no CORS issues and the session cookie works. Create `FE/.../.env.development.local` with `VITE_API_URL=http://127.0.0.1:8000`; the committed `.env` points at the **production** API.
- **Prod:** `VITE_API_URL` is baked in at build time (`Dockerfile`, FE `deploy.yaml`). The BE `CORS_ORIGINS` must contain the exact FE origin.

### 3.2 API layer: RTK Query on the existing axios instance *(Decision D1)*

The current pattern (`SERVICES` map + hand-written thunks + one slice per response) does not scale to ~95 endpoints, and it has no cache invalidation. After an approval, the My Approvals list, dashboard counts, record detail and notification badge must all refresh.

**Recommendation:** use **RTK Query**, which already ships inside `@reduxjs/toolkit` (no new dependency), with a custom `axiosBaseQuery` that reuses `axiosInstance` from `src/helpers/index.ts`, so the existing interceptors keep working.

```
src/api/
  baseApi.ts          createApi + axiosBaseQuery + tagTypes
  types.ts            shared API types (Record, Format, Workflow, Step, Person, ...)
  errors.ts           getApiErrorMessage(err) — reads the BE error envelope (§9.2)
  auth.api.ts         login, me, logout, changePassword
  formats.api.ts      formats, teams, people, folders, repository, approvals
  records.api.ts      call, detail, values, attachments, scan, submit, nok, reverify, return, cft, store, listing, sheet, storage tree
  workflow.api.ts     workflow detail, decide, tasks, stats, approvers
  approvals.api.ts    my-approvals
  repository.api.ts   documents repository, summary, timeline, folders
  documents.api.ts    document metadata, preview-info, file blobs
  changeRequests.api.ts  DCR
  recordChangeRequests.api.ts  RCR
  admin.api.ts        users, roles, departments
  audit.api.ts        audit, modules, summary
  notifications.api.ts  mine, read
  dashboard.api.ts    actions/dashboard
```

Tag types: `Format`, `Record`, `Workflow`, `MyApprovals`, `Notifications`, `Repository`, `DCR`, `RCR`, `Users`, `Roles`, `Teams`, `Departments`, `Audit`, `Stats`. Every mutation invalidates the tags it affects. For example, *decide* invalidates `Record`, `Workflow`, `MyApprovals`, `Notifications` and `Stats`.

Keep `auth` in a plain slice (token + user). Retire `folderSlices`, `formatSlices`, `statsSlice`, `detailsSlice`, `folders/action.ts` and `redux/services/*` once their screens are migrated.

### 3.3 Authentication & session *(Decision D2)*

- On login, store `access_token` in `localStorage["token"]` (today only `loginDetails` is stored). Keep `user` from the login response, then call `GET /api/auth/me` for the full profile (permissions, `is_admin`, `can_approve`, `can_sign`, department).
- **Delete the hard-coded admin JWT in `src/main.tsx:6`.** It is a committed credential. Treat that token's signing secret as compromised and rotate `jwt_secret_key` on the deployed server.
- Add a `<RequireAuth>` wrapper around `MainLayout` routes: no token → `/login`; token present → fetch `/me` once; a 401 is already handled by the axios interceptor.
- Handle `must_change_password: true` from login: redirect to a change-password step (`POST /api/auth/change-password`).
- Logout: `POST /api/auth/logout` (clears the cookie), clear the token and RTK Query cache, go to `/login`.
- The JWT lifetime is **hard-coded to 30 minutes** with no refresh endpoint (`BE/app/services/auth_service.py:22`). Fix it in the BE (§4, B4) so a shift-long session is possible.
- Send cookies too (`withCredentials: true`). This keeps `<iframe>`/`<img>` file URLs working when FE and BE are same-site.

### 3.4 Permission-driven UI

- **Navigation:** hide admin-only screens (Template Builder, Template Repo, Roles & Permissions) unless `me.is_admin`. The format authoring endpoints are all admin-only today (see D6).
- **Buttons:** records, DCRs and RCRs return a server-computed `can{}` object, and workflow steps return `can_act` and `blocked_reason`. **Always drive action buttons from these flags** rather than re-implementing the rules in the FE. Show `blocked_reason` as a tooltip.

### 3.5 Files, previews, downloads *(Decision D3)*

File endpoints need auth: `/api/documents/{id}/file`, `/download` and `/thumbnail`, `/api/formats/{id}/blank`, `/api/records/{id}/attachments/{aid}` and `/api/signatures/{wf}/preview`. An `<iframe src>` cannot send a Bearer header.

**Recommendation:** add a `useAuthedObjectUrl(url)` hook that fetches the file through `axiosInstance` with `responseType: "blob"` and returns `URL.createObjectURL(blob)` (revoked on unmount). It works in dev and prod regardless of cookie or domain setup. For downloads, use the same blob plus an `<a download>`. The BE must add `expose_headers=["Content-Disposition"]` to CORS (§4, B5) so the file name is readable.

### 3.6 Errors, loading, toasts

- The BE replaces FastAPI's `{detail}` with `{"error": {status_code, message, detail, validation_errors?}}` (§9.2). The builder currently reads `error.response.data.detail`, which is always `undefined`.
- Add `getApiErrorMessage(err)`, which prefers `error.detail` (string), then the joined `validation_errors[].message`, then `error.message`. Use it everywhere.
- Replace `alert()`/`window.confirm()` in the builder with `react-toastify` and the existing `CustomDialog`.
- Every list shows a loading skeleton, an empty state and an error state with a retry.

### 3.7 Conventions

- **IDs** are UUID strings. Route params change from mock ids to real ids: `/my-forms/:recordId`, `/my-approvals/:recordId`, `/builder/:formatId`, `/change-request/:id`.
- **Dates:** the BE stores UTC and its helpers use IST (`BE/app/utils/ist.py`). Format in the FE with `Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata" })` in one helper.
- **Types:** hand-write `src/api/types.ts` from §5 and Swagger. Optionally generate them later with `openapi-typescript` from `/openapi.json` (many responses are untyped dicts, so hand-written types are the reliable baseline).
- **Mocks:** delete each mock array as soon as its screen is wired, so no screen silently falls back to fake data.

---

## 4. Blockers found during the review

These must be fixed or consciously accepted **before** the matching FE phase, or the end-to-end flow cannot work. All were verified in code.

| ID | Problem | Evidence | Fix | Owner | Size | Blocks |
|---|---|---|---|---|---|---|
| **B1** | Seeded users **lose approval and signing authority on every server restart.** On boot, `remove_legacy_roles` resets every non-admin user without a custom role to `can_approve=False` and `can_sign=False`. The seed assigns no roles, and the QMS role names are reserved and deleted. | `BE/app/services/role_service.py:102-155`; `ensure_standard_roles` is a no-op | Seed creates custom roles via the role service (e.g. **"Quality Approver"** = documents.view + records.fill + approvals.approve; **"Operator"** = documents.view + records.fill) and assigns one to every seeded person | BE | S | Phases 2–4 |
| **B2** | Auth is **off** by default, so every caller is the admin, and `can_act` refuses admins on steps assigned to other people. Multi-user flow is impossible. | `BE/app/config.py:49`, `auth_service.py:229-286` | Set `AUTHENTICATION_ENABLED=true` in every environment the FE talks to | BE/DevOps | S | Phase 1 |
| **B3** | FE ships a **hard-coded admin JWT** and login never stores the real token | `FE/.../src/main.tsx:6`, `src/redux/slices/auth/action.ts` | Remove; store `access_token`; rotate the server JWT secret | FE + DevOps | S | Phase 1 |
| **B4** | JWT lifetime hard-coded to 30 min; the `ACCESS_TOKEN_EXPIRE_MINUTES` env var is ignored; no refresh endpoint | `BE/app/services/auth_service.py:22,58` | Read the setting (suggest 480 = one shift) | BE | S | Phase 1 |
| **B5** | CORS: `.env.example` omits FE origins; no `expose_headers` | `BE/.env.example`, `app/main.py` | `CORS_ORIGINS` += `http://localhost:5173` and the prod FE origin; `expose_headers=["Content-Disposition"]` | BE | S | Phase 1 (prod) |
| **B6** | **Timezone bug on Postgres**: naive `datetime.utcnow()` compared with tz-aware columns → `TypeError` in overdue checks and RAG refresh. Tests only run on SQLite, so CI does not catch it. | `BE/app/services/workflow_service.py:990`, `record_service.refresh_status`, `tasks_for` | Use tz-aware `datetime.now(timezone.utc)` (or an `_aware()` helper, as in `inspection_report.py`); add a Postgres test job | BE | M | Phases 3–4 on any Postgres env |
| **B7** | Builder-made templates **never produce OK/N-OK**. `form_layout.to_fields` only reads `spec_min`/`spec_max`/`unit` from React items, and the builder UI never sets them. | `BE/app/services/form_layout.py:307-384` | FE: add Unit / Spec min / Spec max / Spec text to the builder's edit panel for Number/Text/Dropdown items (stored on the item) | FE | M | Phase 3 OK/N-OK |
| **B8** | The **Table / Grid** builder element becomes one text field ("Table / Grid"), so its cell readings are not recorded or judged | `form_layout.py:333-384`; `templateBuilder/builder/TableGrid.tsx` | BE: teach `to_fields` the `CustomElement`/`TableGrid` shape (rows × collected columns, spec per row, like the legacy `table` block) — see D4 | BE (+FE) | M | Phase 3 for table forms |
| **B9** | Filling a builder layout has no stable key between a React answer (`field_name`) and a BE value (matched by `id` or `label`, with dedup suffixes "(2)") | `record_service.save_values` (by_id/by_label) | BE: store `layout_key` (the React `field_name`) on each generated field/value and accept it in `PUT /values`; FE maps by `layout_key`. Fallback: match by label in reading order. See D4 | BE + FE | M | Phase 3 |
| **B10** | "Create Folder" in Resources **creates a real placeholder format** (`QF-<timestamp>`, field "Bore diameter") | `FE/.../src/redux/slices/folders/action.ts:39-58` | Use `POST /api/formats/folders` (admin) | FE | S | Phase 2 |
| **B11** | The builder's "Release" calls `/activate`, which requires an approved review, so it always fails. The builder also never sets frequency, PO/OPO/QMS/CFT or work instruction, so `readiness()` fails anyway. | `templateBuilder/builder/index.tsx:430-470`; `format_service.readiness` | Phase 2 adds the responsibilities panel plus Submit-for-approval / Publish-without-approval | FE | L | Phase 2 |
| **B12** | Email approval links are **dormant**: `approval_link_service.issue` is never called, and emails link to `/track?record=` | `BE/app/services/approval_link_service.py`, `notification_service.notify` | Optional (Phase 10): call `issue()` per step assignee and add FE route `/approve/:token` | BE + FE | M | — |
| **B14** | **Capabilities are too coarse for the QMS rules.** The `approvals.approve` capability always grants `records.store`, and `records.fill` grants `records.fill`. Both are *bypass* permissions: the holder may file / fill **any** format's records, not only those where the format names them (`record_service.call_format`, `record_service.store`, `format_service.callable_by`). Every approver role an admin creates in the Roles screen can therefore file every record in the plant. | `BE/app/routers/roles.py` `PERMISSION_CATALOG` | Product decision **D11**. The seed works around it (its role grants only read/approve/sign) | BE + PO | M | Correct access control in prod |
| **B15** ✅ fixed in Phase 4 | **Approvers chosen at submission are not honoured by the record actions.** `approval_overrides` changes who the workflow steps are assigned to. But `RecordAccessPolicy` (`can{}`) and `record_service` (`clear_nok_flag`, `store`, `send_back_for_reverification`, `return_for_correction`, `nok_flagged_to`) still check `format.process_owner_id` / `overall_process_owner_id`. A format that leaves the OPO blank can therefore never have its N-OK flag cleared or its record filed, except by an admin. The fill half was fixed in Phase 3 (see the log) | `app/routers/records.py` `RecordAccessPolicy`, `app/services/record_service.py` | Resolve the effective PO/OPO as `approval_overrides[role]` or the format's person, in one helper used by both | BE | M | Phase 4 |
| **B13** | `.env.example` sets `ENVIRONMENT=production`, so cookies are `Secure` and are not set over `http://localhost` | `BE/.env.example` | Local `.env`: `ENVIRONMENT=development` | Dev | S | Local dev |

Also noted, not blocking:

- `record_service.store` sets stage before validating (relies on rollback).
- No code path sets a record to `cancelled`; cancelling a record's workflow strands the record.
- RCR "implement" changes status only, not record data.
- CFT overdue reminders are not emailed: there is no scheduler, and `remind` only logs.
- `cli.py status` crashes on stale AI references.
- `setup.ps1` writes obsolete AI env vars.

---

## 5. Screen-by-screen API map

Paths are exact. Mind the trailing slashes (§9.1). `{wf}` = workflow id, `{step}` = step id.

### 5.1 Login & session — `login/index.tsx`, `header/Header.tsx`

| UI | API | Mapping |
|---|---|---|
| Log In button | `POST /api/auth/login` `{username, password}` (username may be an email) | → `{access_token, token_type, must_change_password, user{username, full_name, is_admin, role_names}}`; store the token |
| App boot / header chip | `GET /api/auth/me` | `full_name` → chip name and avatar initial; `role_names[0]` or "Administrator" → role line; dashboard greeting "Hi, {first name}" |
| Forced password change | `POST /api/auth/change-password` `{current_password, new_password}` | when `must_change_password` |
| Logout icon | `POST /api/auth/logout` | then clear the token and cache |
| Login errors | 401 → "Invalid username or password"; 429 → "Too many attempts, wait 5 min" (5 failed attempts / 300 s) | |

### 5.2 Dashboard `/` — `dashboard/*`

| Widget | API | Mapping / notes |
|---|---|---|
| KPI "Overall Documents" | `GET /api/actions/dashboard?days=7` | `totals.total`, `totals.growth` → trend |
| KPI "Pending Approvals" | `GET /api/my-approvals?tab=pending&per_page=4` | `counts.pending`; caption `"{counts.overdue} overdue"` |
| KPI "Open Change Requests" | `GET /api/change-requests` + `GET /api/record-change-requests?page_size=1` | DCR `stats.submitted + stats.under_review` + RCR `stats.open` |
| KPI "Active Template" | `GET /api/formats/stats` | `published` |
| Document Activity chart | `GET /api/actions/dashboard?days=7` → `trend` | **Gap (D7):** the chart wants per-day *published / approval / under-review / change-request*; `trend` is inspection buckets. Confirm the bucket keys in Phase 8; if they do not fit, add a BE endpoint `GET /api/dashboard/activity?days=7` |
| Action Required table | same my-approvals call | `items[]`: `document_name` → Document Name; `stage` (label) → Current Approval Step; `due_at` → Due Date; 👁 → `/my-approvals/{record_id}` |
| Recent Activity | `GET /api/audit?page_size=5` | `events[]`: `label` / `summary` → title, `at` → relative time, `module` → icon |
| "Last 7 days" button | pass `days` (7/30/90) to the calls above | |

### 5.3 Resources Library `/resources` — business steps 1–2 (call a released format)

| UI | API | Mapping / notes |
|---|---|---|
| Folder tree + file list | `GET /api/formats/?status=active` (only released formats can be called) | keep `utils/formatMapper.ts` (`folder_path` → tree); `frequency_label` → Type; `team.name` → Department; `code` → Tag; `process_owner.name` → Uploaded by |
| "Create Folder" (admin only) | `POST /api/formats/folders` `{name, parent_path}` | **replaces the junk-format hack (B10)**; admins load the tree from `GET /api/formats/folders` |
| Preview panel | `has_blank` → `GET /api/formats/{id}/blank?inline=true` via blob (§3.5); otherwise render the layout read-only from `GET /api/records/preview/{format_id}` | |
| "File" button (fill this format) | `GET /api/formats/callable` → match by id → if `existing_for_period` → open that record; else `POST /api/records/call` `{format_id, entry_mode:"digital"}` | → navigate `/my-forms/{record.id}`. Show the `period.label` ("Shift/Day/Week …") on the button |
| "Change Request" button | `POST /api/change-requests` `{kind:"change_existing", format_id, title, reason, proposed_change, justification?}` | opens a DCR dialog (new component); only one open DCR per format is allowed (409 → toast) |

### 5.4 My Documents `/my-forms` — `myForms/MyFormsDash.tsx`

| UI | API | Mapping |
|---|---|---|
| "On Verification" / "Draft" tabs | `GET /api/records/documents-listing?tab=verification|draft&q&team_id&page&page_size` | `items[]` → grid: `document_name`, `department.name`, `type`/`frequency`, `start_on`, `last_update`, `stage_label` → status, `last_approval` → "Approval step / approved by"; **add a RAG dot column** from `rag` (🟢🟡🔴 with `rag_label` tooltip) |
| Department filter | `departments[]` from the same response | value = `team_id` |
| Tab badges | `counts{}` | |
| Search | `q` (server-side, debounced 300 ms) | replaces the AG Grid quick filter |
| 👁 View | `/my-forms/{id}` | |
| Track | `/my-forms/{id}?tab=track` | |
| "Approvals" main tab | embeds My Approvals (§5.7) | |

### 5.5 Fill a record `/my-forms/:recordId` — `myForms/FormDetails.tsx` (business steps 2–5)

| UI | API | Mapping / notes |
|---|---|---|
| Load | `GET /api/records/{id}` | `format.title/code/format_revision` → header; `format.work_instruction_ref` + `work_instruction` → collapsible "Work instruction" card (new); `values[]` → inputs; `can.fill` false → read-only |
| Form body | **Mode A (all formats):** generic renderer from `values[]` (`label`, `field_type`, `unit`, `spec_label`, `options`, `required`) — replaces the hard-coded `FIELDS` + `InspectionTable`. **Mode B (builder templates):** `FormFillRenderer` with `format.layout`, answers mapped through `layout_key` (B9) | Ship A first (it works for the seeded formats), then B |
| Save (debounced auto-save + "Save draft") | `PUT /api/records/{id}/values` `{values:[{id, value, remark}]}` | the response returns `in_spec` per value → green ✓ / red "Out of spec (min–max)" beside each input; `observation_status` → OK / N-OK banner. **Replace the raw `fetch()` in `FormFillRenderer.tsx:93`** with the API layer |
| "Attach the scanned hard copy" | `POST /api/records/{id}/scan` (multipart `file`) | a PDF or picture only (a picture is kept as a PDF so signatures can be stamped on it); store the returned `document_id` for submit |
| Photos / evidence (new) | `GET|POST|DELETE /api/records/{id}/attachments[/{aid}]` | multipart `file` + `caption` |
| "Set up Approval" → submit | see §5.6 | |
| "Don't Required Approval" / "Share without approval" | **none** — the process mandates approval | **Remove (D5)** |
| "Copy in My Document" | **none** | Remove or hide (D5) |
| `/resources/file` route | — | Remove; Resources "File" now calls the format and navigates to `/my-forms/{id}` |

### 5.6 Confirm approvers & submit `/my-forms/:recordId/approval` — `myForms/ApprovalSetupPage.tsx`

The BE does **not** take a free-form approval route for records. The route is fixed per format: PO → OPO → CFT (all members) → Final decision. Only the **assignees per role** can be overridden at submit.

> **Found in Phase 0:** a format may be released with its PO / OPO / CFT / QMS left **blank**. `format_service.readiness` only checks the people who *are* named. The approvers are then chosen on the record at submission via `approval_overrides`. This page is therefore **required**, not optional: when a role is blank on the format, the submitter must pick someone for it.

**Reshape the page (D5):**

| UI | API | Mapping |
|---|---|---|
| Route preview | `GET /api/records/{id}` → `route[]`, `responsibilities{}`, `storage_preview`, `cft_target_date` | read-only step cards: "Step 1 · Process Owner approval — Ravi Kumar (signature)", etc.; "Will be filed in: Records / PQ / QF-PQ-001 / 2026 / 10-Oct / 22" |
| "Change person" per step (optional) | `GET /api/formats/{format_id}/people` → `{process_owner[], overall_process_owner[], cft_members[], qms_coordinator[]}` | a select per role → `approval_overrides: {process_owner:[id], …}` |
| Priority card | **not supported for records** | remove, or add BE support (D5) |
| "Start Approval" | `POST /api/records/{id}/submit` `{document_id?, approval_overrides?}` | success → `ApprovalStartedDialog`; if N-OK, also show "N-OK observations have been flagged to {OPO}"; 400 "missing PO/OPO/CFT" → message pointing to the format owner |
| "Skip for now" | — | just navigate back (the record stays in `filling` = draft) |

### 5.7 My Approvals `/my-approvals` — `myApprovals/index.tsx`

| UI | API | Mapping |
|---|---|---|
| Tabs Overdue / Pending / Returned | `GET /api/my-approvals?tab=overdue|pending|returned&search&department&page&per_page=10` | `items[]`: `document_name`, `department`, `assigned_by`, `submitted_on`, `due_at` → status column, `stage`; 👁 → `/my-approvals/{record_id}` |
| Tab counts | `counts{overdue, pending, returned}` | |
| Department filter | `GET /api/my-approvals/departments` → `string[]` | |
| Status filter | **not supported** | replace with a Stage filter (client-side on `stage`) or remove |
| Stats tiles | `GET /api/workflow/tasks/stats` → `{pending, approved_today, returned, overdue}` | relabel the tiles to match |
| New tab "Template approvals" | `GET /api/formats/approvals/mine` → `{approvals:[{format_id, code, title, review}]}` | 👁 → `/builder/{format_id}?review=1` (§5.9) |
| Pagination | `page`, `per_page`, `total_pages` | `CustomPagination` |

### 5.8 Approval review `/my-approvals/:recordId` — `myApprovals/ApprovalReview.tsx` (business steps 6–10)

| UI | API | Mapping / notes |
|---|---|---|
| Load | `GET /api/records/{id}/sheet` + `GET /api/workflow/{workflow_id}` | sheet → Document Summary (format code/title, team, period, filled_by/at, observation, NOK summary, readings with in-spec flags); workflow → current step (`can_act`, `blocked_reason`, `requires_signature`, `qms_stage`, `approval_mode`, `outstanding`) |
| Approval Details card | `sheet.approval` | `assigned_to` → Currently assigned to; `submitted_by/at`; `priority` |
| Approval Timeline | `workflow.steps[]` (+ `events[]`) | `ApprovalTimeline` `TimelineStep`: `order`→step, `name`→title, `role`/`department`, `status` (approved→Completed, current→In Progress, pending→Pending), `decided_by`/`decided_at`, `comment` → notes, `signature.dataUrl` → signature thumbnail |
| Document preview / "View / Open" | `GET /api/signatures/{wf}/preview` (PDF stamped with signatures) or `sheet.document.file_url` | via the blob hook (§3.5) |
| RAG + NOK banner | `record.rag`, `rag_label`, `nok_open`, `nok_summary`, `cft_target_date`, `reverify_count` | red banner when `nok_open` |
| **Approve** (PO / OPO / Final) | `POST /api/workflow/{wf}/steps/{step}/decide` `{action:"approve", comment, signature?}` | **Signature pad required** when `step.requires_signature`: canvas → `data:image/png;base64,…` (≤ 2 MB) → `signature:{dataUrl, name, designation, method:"draw"}`. User needs `me.can_sign` |
| **Reject** (PO / OPO) | decide `{action:"reject", reason, comment}` | returns the record for correction |
| **Request changes** | decide `{action:"changes", comment}` | |
| **CFT step: Agree / Object** | `POST /api/records/{id}/cft-opinion` `{agrees: true|false, comment}` | relabel the buttons when `qms_stage === "cft_review"`; show who is still `outstanding` |
| **Final decision: Send back to CFT** | `POST /api/records/{id}/reverify` `{reason}` | shown when `can.send_back` |
| **Clear N-OK flag** (OPO) | `POST /api/records/{id}/nok/clear` `{note}` | shown when `can.clear_nok` |
| **File / Store record** (OPO, after final approval) | `POST /api/records/{id}/store` | shown when `can.store`; success → toast "Filed in {storage_path}" |
| Button visibility | `record.can{fill, submit, clear_nok, send_back, return_for_correction, amend, store}` + `step.can_act` | never show an action the server will refuse |

### 5.9 Template Builder `/builder`, detail `/builder/:id`, designer `/builder/:id/build` (admin)

| UI | API | Mapping / notes |
|---|---|---|
| Stats tiles | `GET /api/formats/stats` (already wired) | |
| Tabs On Verification / Change Request / Draft (+ "Published") | `GET /api/formats/?tab=on_verification|change_request|draft|all` | `formats[]` + `builder_status`; `summary{}` → tab counts. Replaces `builderRows` |
| "New Template" | navigate `/builder/new/build` | designer without `format_id` |
| "Upload File" | `POST /api/ocr/template` (multipart) → the designer → `POST /api/formats/` | an Excel workbook, PDF or picture becomes an editable template (§13) |
| Detail page | `GET /api/formats/{id}` (fields, readiness, versions, previous_revisions) + `GET /api/formats/{id}/approval` + `/approval/history` | Document Summary from format metadata; preview = blank file or a layout render; Timeline = review `steps[]`/`decisions[]`; show `readiness[]` problems as a checklist |
| Detail "Edit" | `/builder/{id}/build?format_id={id}` (drafts only; active → raise a DCR) | |
| Detail "Delete" | **no delete endpoint** | Active → "Withdraw" `POST /api/formats/{id}/withdraw`; drafts → D6 |
| Review decision (when opened from Template approvals) | `POST /api/formats/{id}/approval/decision` `{decision:"approve"|"reject", comment}` | last approval auto-activates the format |
| **Designer — existing** | `GET /api/formats/{id}`, `POST /api/formats/`, `PUT /api/formats/{id}`, `GET /api/formats/teams` | keep |
| Designer — **new "Responsibilities & filing" panel** (B11) | `GET /api/formats/people` (or `/{id}/people`) | frequency select (shift/daily/weekly/monthly/quarterly/half_yearly/yearly/per_event; **stop hard-coding "daily"**), `process_owner_id`, `overall_process_owner_id`, `qms_coordinator_id`, `cft_member_ids[]`, `cft_target_days`, `work_instruction_ref`, `work_instruction`, `storage_path` (folder picker from `GET /api/formats/folders`) |
| Designer — spec properties (B7) | stored on each layout item | unit, spec_min, spec_max, spec_text on Number/Text/Dropdown items |
| Designer — "Release" → **"Submit for approval"** | `GET /api/formats/approvers?role_id=` → `POST /api/formats/{id}/submit-approval` `{steps:[{name, reviewer_ids[], mode, due_days}], priority}` | reuse the step-card UI from `ApprovalSetupPage` here (it fits this API) |
| Designer — "Publish without approval" (admin, audited) | `POST /api/formats/{id}/publish-without-approval` | confirm dialog |
| Designer — readiness | `readiness[]` from the format response | block submit and list the problems |
| Starter layout for new templates | `GET /api/formats/starter-layout` | optional |

### 5.10 Template Repo `/builder-repo` (admin) — `templateRepo/*`

| UI | API | Mapping |
|---|---|---|
| Tree + list | `GET /api/formats/repository` → `{templates[], folders[tree with templates[]], total}` | **Rewrite `utils/folderMapper.ts`**: the BE returns `templates[{id, code, title, team, frequency_label, latest_version, released_version, version_count, versions[]}]` nested in `folders[].templates`, not the `{name, type, department, uploadedBy, folderId}` the FE type assumes |
| Template detail + version history | `GET /api/formats/{id}` → `versions[]`, `previous_revisions[]` | replaces `VERSION_HISTORY` and the hard-coded summary |
| Preview / download blank | `GET /api/formats/{id}/blank?inline=true` | blob hook |

### 5.11 Doc Repository `/doc-repo` — filed records (business step 10)

| UI | API | Mapping |
|---|---|---|
| Folder tree (date/month folders) + list | `GET /api/documents/repository?search&folder_path&team_id&format_id&filed_date&date_from&date_to&page&page_size` | `folders[{name, path, records_count, total_records, is_pinned, children}]` → `CustomFolderTree`; `documents[]` → rows (`document_name`, `form_code`, `department`, `type`, `filed_by_name`, `filed_date`, `period`) |
| Detail summary | `GET /api/documents/repository/{record_id}/summary` | replaces `qualityControlDocuments` |
| Approval timeline | `GET /api/documents/repository/{record_id}/approval-timeline` | `ApprovalTimeline` |
| Preview / download | `GET /api/documents/{document_id}/file` / `/download` (+ `/preview-info` for the mode) | blob hook |
| Rename folder | `PATCH /api/documents/repository/folders/rename` `{folder_path, new_name}` | needs `documents.write` (admin in practice) |
| Pin folder | `PUT /api/documents/repository/folders/pin` `{folder_path, pinned}` | |
| Remove create/delete folder actions | — | filing folders are created by the system from frequency |

### 5.12 Change Requests `/request`, `/change-request/:id` — business step 11 *(Decision D8)*

The FE tabs (Open / Approved / Implemented / Not approved) match **Record Change Requests (RCR)**. The process diagram's change request is the **Document/Format Change Request (DCR)**. Both exist in the BE. **Recommendation:** add a top switch, *Record changes* | *Format changes (DCR)*.

| UI | RCR API (`/api/record-change-requests`) | DCR API (`/api/change-requests`) |
|---|---|---|
| List + tabs | `GET ?status=open|approved|implemented|not_approved&department&search&mine&waiting&page&page_size` → `requests[]`, `stats{}`, `waiting_on_me` | `GET ?status=submitted|under_review|approved|rejected|implemented&team_id&format_id&mine&waiting` → `requests[]`, `stats{}` |
| Detail | `GET /{id}` → record summary, `fields[]`, `document`, `can{edit, assign, decide, implement}` | `GET /{id}` → `format`, `current_state`, `proposed_change`, `justification`, `coordinator`, `can{decide, execute}` |
| Raise | `POST` `{record_id, title?, reason, assigned_to_id?}` (from the record page: "Request change") | `POST` `{kind, format_id?/team_id?, title, reason, current_state?, proposed_change, justification?}` (from Resources / Template Repo) |
| Approved / Not approved buttons | `POST /{id}/decide` `{action:"approve"|"not_approved", comment}` | `POST /{id}/review` (start) then `POST /{id}/decide` `{action:"approve"|"reject", comment}` |
| Edit | `PATCH /{id}` `{title, reason}` | — |
| Assign | `POST /{id}/assign` `{assigned_to_id}` | — |
| Implement / Execute | `POST /{id}/implement` `{note}` | `POST /{id}/execute` (optional overrides) → creates the new revision / new format draft → link "Open draft in builder" |

### 5.13 Roles & Permissions `/people-teams` (admin) — `peopleAndTeams/*`

| UI | API | Mapping / notes |
|---|---|---|
| Teams tab | `GET /api/formats/teams` → `teams[{id, code, name, description, is_active, format_count, people[]}]`, `unassigned[]` | `Team` type: `code`, `name`, `members = people.length`, initials from `people[].name` |
| New Team dialog | `POST /api/formats/teams` `{code, name, description}`; edit `PUT /api/formats/teams/{id}`; retire/restore `POST /api/formats/teams/{id}/retire|restore` | |
| People tab | `GET /api/auth/users` | `full_name`, `job_title`, `email`, `department`, `role_names`, `is_active` → status; derive the team name from `quality_team_id` |
| Add Person dialog | 1) `POST /api/auth/users` `{username, email, full_name, password, role_id, department_id, job_title}` 2) `PUT /api/auth/users/{id}` `{quality_team_id}` | "Account type" (Admin/Manager/Member) → **role select** from `GET /api/roles`; Department select from `GET /api/departments`; Team select from teams |
| View / edit / deactivate / delete person | `GET|PUT|DELETE /api/auth/users/{id}`; change role `PUT /api/roles/users/{id}` `{role_id}` | `PUT` rejects `can_approve`/`can_sign`/`account_type` (409) — authority comes from the role |
| Roles list / detail | `GET /api/roles`, `GET /api/roles/{id}`, members = users filtered by `role_ids` | |
| Add / edit role | `GET /api/roles/permissions` (4 capabilities) → `POST /api/roles` `{name, description, permissions[]}` / `PUT /api/roles/{id}` / `DELETE` | reserved names rejected (409) |
| Departments (new small section) | `GET|POST /api/departments`, `DELETE /api/departments/{id}` | bare paths, no trailing slash |

### 5.14 Activity Log `/activity-log`

| UI | API | Mapping |
|---|---|---|
| Grid | `GET /api/audit?q&action&module&date_from&date_to&page&page_size` | `events[]`: `at` → timestamp, `user` → user, `label` → action, `module`, `summary`/`resource_id` → document; server-side pagination via `pagination{}` |
| Module filter | `GET /api/audit/modules` | |
| Date range | `date_from` / `date_to` (YYYY-MM-DD) | |

### 5.15 Notifications — header bell, popup, `/notifications`

| UI | API | Mapping |
|---|---|---|
| Bell badge | `GET /api/records/notifications/mine?unread_only=true&limit=1` → `unread` | poll every 60 s and on window focus (RTK Query `pollingInterval`); invalidated by every workflow mutation |
| Popup (latest 5) / page | `GET /api/records/notifications/mine?limit=50` → `notifications[{id, kind, subject, body, related_type, related_id, read, created_at}]` | `kind` → type badge (record.*, dcr.*, record_change_request.*, action.*, inspection.*) |
| Mark read / mark all | `POST /api/records/notifications/read` `{ids:[…]}` / `{}` | |
| Click-through | `related_type`/`related_id` → record → `/my-approvals/{id}` if the user has an action on it, else `/my-forms/{id}`; DCR/RCR → `/change-request/{id}` | |
| Admin: email outbox (optional) | `GET /api/records/notifications/outbox` → `mail_configured`, delivery `status`/`error` | useful for SMTP troubleshooting |

### 5.16 Settings `/settings`

| UI | API | Notes |
|---|---|---|
| Profile card | `GET /api/auth/me` (read-only) | non-admins cannot edit their own profile (user `PUT` is admin-only) |
| Change password (new) | `POST /api/auth/change-password` | |
| Notification preferences | **no BE support** | keep in `localStorage`, labelled "on this device", or hide (out of scope) |
| Appearance | local only | |

### 5.17 Not yet represented in the FE (optional screens)

| Capability | API | Suggestion |
|---|---|---|
| Storage tree of filed records by team | `GET /api/records/storage/tree?team_id` | Covered by the Doc Repository; skip |
| Corrective/preventive actions (CAPA) for N-OK | `/api/actions*` | Phase 10: "Raise corrective action" on N-OK records |
| Signature placement on the PDF | `/api/signatures/{wf}/layout*` | Phase 10 |
| Workflow escalate / remind / cancel | `/api/workflow/{wf}/escalate|remind|cancel` | Admin actions on the review page (Phase 10) |
| Email-link approval | `/api/approve/{token}` | Phase 10 with B12 |

---

## 6. Phased implementation plan

Phases are ordered by dependency. Each phase ends with something demonstrable. Phases 5–8 are independent of each other and can run in parallel once Phase 4 is done.

```
P0 Env & BE readiness ─► P1 API foundation & auth ─► P2 Templates ─► P3 Fill & submit ─► P4 Approval chain
                                                                                         ├─► P5 Repository
                                                                                         ├─► P6 Change requests
                                                                                         ├─► P7 People & roles
                                                                                         └─► P8 Dashboard, notifications, log, settings
                                                                                                   └─► P9 Hardening & release
```

### Phase 0 — Environment & backend readiness

| Step | Task | Owner | Size |
|---|---|---|---|
| 0.1 | Run the BE locally (README "Backend"). Use SQLite for speed (`DATABASE_URL=sqlite:///./data/documents.db`), **and** keep one Postgres env for B6 | BE | S |
| 0.2 | Local `.env`: `AUTHENTICATION_ENABLED=true`, `ENVIRONMENT=development`, `CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173`, `APP_BASE_URL=http://localhost:5173`, `SECRET_KEY=<random>` | BE | S |
| 0.3 | **B1** — seed creates the "Quality Approver" and "Operator" custom roles and assigns them; verify authority survives a restart (`GET /api/admin/check-permissions/r.kumar`) | BE | S |
| 0.4 | **B4** — honour `ACCESS_TOKEN_EXPIRE_MINUTES` in `auth_service.py` | BE | S |
| 0.5 | **B5** — `expose_headers=["Content-Disposition"]` in CORS; update `.env.example` origins | BE | S |
| 0.6 | **B6** — tz-aware datetime comparisons; add a Postgres job to BE CI | BE | M |
| 0.7 | FE: add `.env.development.local` (`VITE_API_URL=http://127.0.0.1:8000`); `npm ci`; `npm run dev` | FE | S |
| 0.8 | Run `python scripts/validate_workflow.py` against the local server as the BE baseline | QA | S |

**Done when:** after a BE restart, `validate_workflow.py` passes and the FE dev server loads the login page with `/api` proxied to the local BE.

### Phase 1 — API foundation & authentication

| Step | Task | Files | Owner | Size |
|---|---|---|---|---|
| 1.1 | **B3** — delete the hard-coded JWT; login stores `access_token`; fix `fetchDetails` (it reads `res.data`, but the service already returns `data`) | `src/main.tsx`, `src/redux/slices/auth/*` | FE | S |
| 1.2 | Create `src/api/baseApi.ts` (RTK Query + `axiosBaseQuery` over `axiosInstance`, `withCredentials: true`), `errors.ts`, `types.ts`; register in `store.ts` | `src/api/*`, `src/redux/store.ts` | FE | M |
| 1.3 | `auth.api.ts` (login/me/logout/changePassword); `RequireAuth` route guard; `must_change_password` screen; logout via API | `src/App.tsx`, `src/layout/*`, `src/login/*` | FE | M |
| 1.4 | Header shows the real user; sidebar hides admin-only items unless `is_admin` | `header/Header.tsx`, `sidebar/Sidebar.tsx` | FE | S |
| 1.5 | Shared UI helpers: `useAuthedObjectUrl`, `formatDateIST`, `<RagDot>`, `<StageChip>`, loading/empty/error states | `src/helpers`, `src/base/*` | FE | M |
| 1.6 | Remove duplicate `/notifications` route and duplicate `<Provider>` (in both `main.tsx` and `App.tsx`) | `src/App.tsx` | FE | S |

**Done when:** you can log in as `r.kumar` and as `admin` with real tokens, the header shows the right person, refreshing keeps the session, 401 → login, and logout works.

### Phase 2 — Templates: authoring, release, resources (business step 1)

| Step | Task | Owner | Size |
|---|---|---|---|
| 2.1 | Template Builder list from `GET /api/formats/?tab=…`; delete `templateBuilder/data.ts` | FE | M |
| 2.2 | Designer: Responsibilities & filing panel (frequency, PO, OPO, QMS, CFT, target days, work instruction, storage path) — **B11** | FE | L |
| 2.3 | Designer: spec properties on items (unit, min, max, text) — **B7** | FE | M |
| 2.4 | BE: `to_fields` support for TableGrid (**B8**) and `layout_key` on fields/values (**B9**) — per D4 | BE | M |
| 2.5 | Designer: replace Release with Submit-for-approval (reviewer steps via `/api/formats/approvers`) and Publish-without-approval; show `readiness[]`; toasts instead of `alert` | FE | M |
| 2.6 | Template detail page from `GET /api/formats/{id}` + approval/history; Edit; Withdraw; review decision (approve/reject) | FE | M |
| 2.7 | "Template approvals" tab in My Approvals (`/api/formats/approvals/mine`) | FE | S |
| 2.8 | Resources Library: active formats, folder creation via `/api/formats/folders` (**B10**), blank preview, DCR dialog | FE | M |
| 2.9 | Template Repo: rewrite `folderMapper`; version history from `versions[]` | FE | M |
| 2.10 | Upload blank file (`POST /api/formats/{id}/blank`) | FE | S |

**Done when:** an admin builds a new template with a Number field (spec 10–12 mm) and a table, assigns PO/OPO/QMS/CFT, submits it for approval, the reviewer approves it, and it appears as **active** in Resources.

### Phase 3 — Fill & submit records (business steps 2–5)

| Step | Task | Owner | Size |
|---|---|---|---|
| 3.1 | Resources "File" → callable/existing-for-period → `POST /api/records/call` → `/my-forms/{id}` | FE | S |
| 3.2 | `FormDetails` Mode A: generic renderer from `values[]` with live in-spec feedback, auto-save (`PUT /values`), OK/N-OK banner, work-instruction card | FE | L |
| 3.3 | `FormDetails` Mode B: `FormFillRenderer` for builder layouts mapped through `layout_key`; replace the raw `fetch` | FE | M |
| 3.4 | Scan upload and attachments | FE | M |
| 3.5 | Reshaped approval page: route preview, per-role override, submit, N-OK message (D5) | FE | M |
| 3.6 | My Documents grid from `documents-listing` with a RAG column, tab counts, department filter, server search/pagination; delete `templateRows` | FE | M |
| 3.7 | Track Status from `GET /api/records/{id}` + `GET /api/workflow/{wf}` (summary + timeline + RAG); delete `approvalSteps`/`approvalSummary` mocks | FE | M |

**Done when:** `r.kumar` fills QF-PQ-001 with one out-of-spec reading, submits it, and sees 🔴 N-OK flagged. The record appears under On Verification with stage "PO approval", and a notification row exists for the PO and OPO (`GET /api/records/notifications/outbox` as admin).

### Phase 4 — Approval chain (business steps 6–10)

| Step | Task | Owner | Size |
|---|---|---|---|
| 4.1 | My Approvals list (tabs, counts, departments, pagination, stats tiles); delete `approvalRows` | FE | M |
| 4.2 | Approval Review page: sheet + workflow load, summary, preview (stamped PDF), timeline | FE | M |
| 4.3 | **Signature pad** component (canvas → PNG data URL, clear/undo, "type name" fallback) | FE | M |
| 4.4 | Decide actions: Approve (with signature when required) / Reject (reason) / Request changes; dialogs from `ActionDialogs.tsx` | FE | M |
| 4.5 | CFT Agree / Object (`/cft-opinion`), outstanding members; Final decision "Send back to CFT" (`/reverify`) | FE | M |
| 4.6 | OPO: Clear N-OK flag (`/nok/clear`) and File record (`/store`) | FE | S |
| 4.7 | All buttons driven by `can{}` / `can_act`; `blocked_reason` tooltips; cache invalidation across lists, counts and badges | FE | S |

**Done when:** acceptance scenarios A, B and C (§7) pass in the browser with real users.

### Phase 5 — Records repository (business step 10, "stored on server")

| Step | Task | Owner | Size |
|---|---|---|---|
| 5.1 | Doc Repository tree + list + filters + pagination from `/api/documents/repository`; delete `docRepository/data.ts` | FE | M |
| 5.2 | Detail: summary, approval timeline, file preview/download | FE | M |
| 5.3 | Folder rename (admin) and pin; remove manual create/delete | FE | S |

**Done when:** the record stored in Phase 4 appears under its frequency folder (the format's `storage_path` root, or the default `Records / <team> / <code>`, then `2026 / 10-Oct / 22` for a daily format) with its signed PDF.

### Phase 6 — Change management (business step 11)

| Step | Task | Owner | Size |
|---|---|---|---|
| 6.1 | Change Request page with the *Record changes* / *Format changes* switch (D8); lists and tabs from the APIs; delete `changeRequestRows` | FE | M |
| 6.2 | RCR detail: decide, edit, assign, implement; "Request change" on the record page | FE | M |
| 6.3 | DCR detail: review → decide → execute; "Open draft in builder" link to the new revision | FE | M |

**Done when:** acceptance scenario D (§7) passes.

### Phase 7 — People, teams, roles, departments (admin)

| Step | Task | Owner | Size |
|---|---|---|---|
| 7.1 | Teams tab (list, create, edit, retire/restore) | FE | M |
| 7.2 | People tab (list, add with role/department/team, edit, deactivate, delete) | FE | M |
| 7.3 | Roles (list, detail with members, create/edit with the 4 capabilities, delete) and Departments | FE | M |
| 7.4 | Delete `people`, `teams`, `departments`, `roles` and `teamMembers` mocks | FE | S |

**Done when:** an admin creates a person with the "Quality Approver" role, assigns them as CFT on a format, and that person can log in and agree in a CFT review.

### Phase 8 — Dashboard, notifications, activity log, settings

| Step | Task | Owner | Size |
|---|---|---|---|
| 8.1 | Dashboard KPIs, Action Required, Recent Activity; range selector | FE | M |
| 8.2 | Document Activity chart — confirm the `trend` shape; add the BE endpoint if needed (D7) | FE (+BE) | M |
| 8.3 | Notification badge (polling), popup, page, mark-read, click-through | FE | M |
| 8.4 | Activity Log from `/api/audit` with server pagination and filters | FE | S |
| 8.5 | Settings: profile from `/me`, change password; local-only preferences | FE | S |

### Phase 9 — Hardening & release

| Step | Task | Owner | Size |
|---|---|---|---|
| 9.1 | Role matrix test: each seeded user sees only what they may act on (§7, scenario E) | QA | M |
| 9.2 | Postgres run of the full scenario set (catches B6-type issues) | QA/BE | M |
| 9.3 | `grep` for leftover mock imports (`constants/data`, `docRepository/data`, `templateBuilder/data`); delete the unused files | FE | S |
| 9.4 | `npm run lint` and `npm run build` clean; BE `pytest -q` green | FE/BE | S |
| 9.5 | Prod config: FE `VITE_API_URL`; BE `CORS_ORIGINS` = FE prod origin, `AUTHENTICATION_ENABLED=true`, `APP_BASE_URL` = FE prod URL, SMTP settings, rotated `SECRET_KEY`/JWT secret | DevOps | S |
| 9.6 | Optional: Playwright smoke test of scenario A in CI | QA | M |

---

## 7. End-to-end acceptance scenarios

Seeded people (password `Harman@2026` for everyone, from `BE/scripts/seed_quality_records.py`):

| User | Name | Role in format **QF-PQ-001 — In-process dimensional check** (daily) |
|---|---|---|
| `admin` | System Administrator | builds and releases formats |
| `r.kumar` | Ravi Kumar | **Process Owner** |
| `s.iyer` | Sunita Iyer | **Overall Process Owner** |
| `a.deshmukh`, `p.nair` | Anil Deshmukh, Priya Nair | **CFT members** |
| `m.shaikh` | Mohammed Shaikh | **QMS Coordinator** |
| `a.sharma` | Aryan Sharma | Process Owner – Assembly (alternate) |
| `k.reddy` / `d.varma` | Kavitha Reddy / Deepak Varma | PO / OPO for QF-SQ-002 (Supplier Quality, weekly) |

**A — Golden path (all OK).**
1. `r.kumar` opens Resources and files QF-PQ-001, enters in-spec readings and submits. → 🟡 `po_approval`.
2. `r.kumar` approves and signs from My Approvals. → `opo_approval`, email/notification to `s.iyer`.
3. `s.iyer` approves and signs. → 🟢 `cft_review` with a target date.
4. `a.deshmukh` and `p.nair` both agree. → `final_decision`.
5. `r.kumar` approves the final decision with a signature.
6. `s.iyer` files the record. → `stored`; it appears in Doc Repository under the day folder with the signed PDF.

**B — N-OK path.** Same as A, but with one reading out of spec. At submit: 🔴, N-OK flag notification to `s.iyer`. Filing is refused while the flag is open. `s.iyer` clears the flag with a note → filing succeeds.

**C — Rejection loops.**
- (i) `s.iyer` rejects at OPO → the record returns to `r.kumar` in `filling`; he fixes and resubmits → a fresh chain starts.
- (ii) At the final decision, `r.kumar` sends it back to CFT → 🔴, `reverify_count = 1`, the CFT re-answers.

**D — Change requests.**
- DCR: `r.kumar` raises "change existing" on QF-PQ-001 → `m.shaikh` gets a notification → review → approve → execute → a new draft revision opens in the builder → admin releases it via the review → the old revision is superseded.
- RCR: raise on a filled record → assign → approve → implement.

**E — Access control.**
- `p.nair` (CFT only) sees no Approve button at the PO step and no admin nav.
- A non-admin opening `/people-teams` is redirected.
- An expired token → login.

---

## 8. Decisions needed from the team

Recommended options are marked ✅. Please confirm or change them before Phase 1.

| ID | Decision | Options | Recommendation |
|---|---|---|---|
| **D1** | FE data layer | a) RTK Query over the existing axios ✅ · b) extend the current thunks/slices · c) add TanStack Query | a: no new dependency, built-in caching/invalidation/polling, keeps the interceptors |
| **D2** | Auth transport | a) Bearer token in localStorage + cookie as backup ✅ · b) cookie only | a: matches the current interceptor; the cookie still helps file URLs. Requires B4 |
| **D3** | Authenticated file previews | a) blob + object URL ✅ · b) rely on the session cookie in `<iframe>` | a: works across domains and with Bearer tokens |
| **D4** | Builder layout ↔ record values | a) BE adds `layout_key` + TableGrid in `to_fields` ✅ · b) FE-only label matching | a: deterministic; b is fragile with duplicate "Placeholder Label" labels. **Done in Phase 2.** **Refined:** records are filled with our own controlled layout renderer (Phase 3), not `ReactFormGenerator`. The generator reads a custom element's value from `ref.current.value` and never forwards `handleChange`, so table readings could not be captured |
| **D5** | Record approval UI | a) reshape to "confirm approvers" (fixed QMS route + per-role overrides), remove "without approval" and "copy" ✅ · b) keep the free-form step builder (needs large BE changes) | a: matches the mandated process and the existing BE. The priority field: drop it, or BE adds `priority` to submit (S) |
| **D6** | Template authoring rights and draft delete | a) admin-only for now; drafts get "Withdraw"/hide ✅ · b) BE accepts `formats.manage` for authoring + adds `DELETE` for drafts | a for the first release; b as a follow-up if QMS staff must author |
| **D7** | Document Activity chart data | a) reuse `actions/dashboard.trend` if its keys fit · b) BE adds `/api/dashboard/activity` | **Done (a):** the trend buckets carry passed / failed / open / filed per period, and the chart shows those |
| **D8** | Change Request page scope | a) one page with a *Record / Format (DCR)* switch ✅ · b) DCR inside Template Builder, RCR on its own page | a: one place for "requests waiting on me" |
| **D9** | Email | configure SMTP in staging now, or rely on in-app notifications until UAT | in-app first; SMTP before UAT |
| **D10** | Email-link approvals (B12) | now or later | later (Phase 10) |
| **D11** | Capability model (B14) | a) split "Approval" from new supervisor capabilities "Fill any format" / "File any record" (BE catalog change) · b) keep as is and document that approvers can file anything | a: the QMS process ties each act to the person named on the format |

---

## 9. Reference: API conventions & gotchas

### 9.1 Trailing slashes matter

A catch-all `GET /{path:path}` disables FastAPI's slash redirect. A wrong spelling returns **404** (GET) or **405** (POST/PUT).

| Works with **either** `""` or `"/"` | Works **only without** a slash | Works **only with** a slash |
|---|---|---|
| `/api/formats`, `/api/records`, `/api/workflow`, `/api/audit`, `/api/actions`, `/api/change-requests`, `/api/record-change-requests` | `/api/roles`, `/api/departments`, `/api/my-approvals`, `/api/documents/repository` | `/api/health/`, `/api/settings/`, `/api/settings/health/` |

Rule for the FE: define every path once in the `*.api.ts` files and never build them by string-concatenating ids onto a base that ends with `/`. (`deleteService` in `redux/services/global.ts` produces `api/formats//id`.)

### 9.2 Error envelope

```json
{ "error": { "status_code": 409, "message": "Conflict", "detail": "A change request is already open for this format.",
             "path": "/api/change-requests", "method": "POST", "timestamp": "…",
             "validation_errors": [ { "field": "body -> title", "message": "Field required", "type": "missing" } ] } }
```

`detail` can be an object for some 409/422 responses. `GET /api/approve/{token}` returns `200 {ok:false, reason}` instead.

### 9.3 Pagination is not uniform

| Endpoint | Request | Response |
|---|---|---|
| `/api/audit`, `/api/documents/repository` | `page`, `page_size` | `pagination{page, page_size, total, total_pages}` |
| `/api/records/documents-listing` | `page`, `page_size` | top-level `page, page_size, total, total_pages` |
| `/api/record-change-requests` | `page`, `page_size` | `total, page, page_size, pages` |
| `/api/my-approvals` | `page`, **`per_page`** | `page, per_page, total, total_pages` |
| records list, workflow list, notifications | `limit` | not paginated |

Normalise these in each endpoint's `transformResponse` to `{items, page, pageSize, total, totalPages}`, so `CustomPagination` has a single shape.

### 9.4 Rate limiting

- 100 requests / 60 s per IP per path.
- Login: 5 *failed* attempts / 300 s.
- A 429 has **no CORS headers** (the limiter wraps CORS), so in prod the browser reports it as a CORS error. Keep polling at ≥ 30 s and avoid request storms; RTK Query de-duplication helps.

### 9.5 Status vocabularies (FE display labels)

| Domain | Values |
|---|---|
| Record stage | filling · po_approval · opo_approval · cft_review · final_decision · stored · cancelled (use `stage_label` from the API) |
| RAG | green "Ok for final review" · yellow "Filling in progress" · red "Needs to reverify with CFT" (use `rag_label`) |
| Observation | ok · not_ok |
| Format status | draft · in_review · active · superseded · withdrawn |
| Workflow | draft · active · approved · rejected · changes_requested · cancelled · published |
| Step | pending · current · approved · rejected · changes_requested · skipped |
| DCR | submitted · under_review · approved · rejected · implemented |
| RCR | open · approved · not_approved · implemented |
| Frequency | shift · daily · weekly · monthly · quarterly · half_yearly · yearly · per_event |

---

## 10. Out of scope / later

These are not needed for the first integrated release; each is listed here so it is a conscious choice.

- Email-link approvals (B12) and the `/approve/:token` page.
- Scheduled reminders and CFT-overdue emails (no scheduler in the BE).
- CAPA screens (`/api/actions`).
- Signature placement editor (`/api/signatures/*/layout`).
- Workflow escalate/remind/cancel admin tools.
- OCR / AI digitisation of paper formats (removed from the BE).
- Per-user notification preferences (needs a BE model).
- Admin system settings, backups and health screens (`/api/settings`, `/api/backup`, `/api/health`); Swagger covers them for now.
- BE clean-up: dead `format_*.py` routers, stale README/TESTING references to OCR, `cli.py status` crash, `setup.ps1` AI variables.
- `approval_link_service` compares local naive `datetime.now()` on both sides; switch it to UTC-aware when B12 is picked up.

---

## 11. Progress log

### Phase 0 — Environment & backend readiness ✅ (2026-10-22)

| Step | Change | Files |
|---|---|---|
| 0.1 / 0.2 | Local BE on SQLite. `BE/.env` (git-ignored): auth **on**, `ENVIRONMENT=development`, token 480 min, Vite origins in CORS, `APP_BASE_URL=http://localhost:5173` | `BE/.env` |
| 0.3 (B1) | Seed creates the **"Quality Approver"** role (read / approve / sign, the legacy *signatory* set; see B14) and assigns it to every seeded person, including on re-runs against an existing DB | `BE/scripts/seed_quality_records.py` |
| 0.4 (B4) | Login honours `ACCESS_TOKEN_EXPIRE_MINUTES` | `BE/app/routers/auth.py` |
| 0.5 (B5) | CORS `expose_headers = Content-Disposition, X-Signature-Count`; `.env.example` lists the Vite origins | `BE/app/main.py`, `BE/.env.example` |
| 0.6 (B6) | Python-side datetime comparisons normalised to UTC-aware (`is_overdue`, task sort, RAG CFT-overdue) | `BE/app/services/workflow_service.py`, `BE/app/services/record_service.py` |
| 0.7 | `FE/.env.development.local` → `VITE_API_URL=http://127.0.0.1:8000` (git-ignored) | FE |
| 0.8 | `validate_workflow.py` updated to the current rules: release needs an approved review (it now uses the audited publish-without-approval); responsibilities may be blank | `BE/scripts/validate_workflow.py` |

**Verified:**
- `pytest`: 204 passed.
- After a server restart: `r.kumar` and `s.iyer` keep `can_approve` / `can_sign`; the token lasts 480 min; no token → 401; the CORS preflight from :5173 is allowed.
- `validate_workflow.py`: **106/106 checks passed**.

Still open: B6 on a real PostgreSQL instance (step 9.2) and a Postgres CI job.

### Phase 1 — API foundation & authentication ✅ (2026-10-22)

| Step | Change | Files |
|---|---|---|
| 1.1 (B3) | Hard-coded admin JWT removed; login stores the real `access_token` | `src/main.tsx`, `src/login/index.tsx` |
| 1.2 | RTK Query API slice over the existing axios instance; error-envelope parser; session helpers. axios sends cookies and serialises repeated query keys; empty params are dropped | `src/api/baseApi.ts`, `src/api/errors.ts`, `src/api/session.ts`, `src/helpers/index.ts`, `src/redux/store.ts` |
| 1.3 | `auth.api.ts` (login / me / logout / change-password); `RequireAuth` + `RequireAdmin` route guards; forced password change on login; return to the requested page after login | `src/api/auth.api.ts`, `src/layout/RequireAuth.tsx`, `src/App.tsx`, `src/login/index.tsx` |
| 1.4 | Header shows the signed-in person and role, and logout calls the API and clears the cache; the sidebar hides Template Builder / Template Repo / Roles & Permissions for non-admins | `src/header/Header.tsx`, `src/sidebar/Sidebar.tsx` |
| 1.5 | Shared helpers: IST date formatting, `useAuthedObjectUrl` (blob previews), `RagDot`, `PageLoader` / `ErrorState` | `src/utils/date.ts`, `src/hooks/useAuthedObjectUrl.ts`, `src/base/status/RagDot.tsx`, `src/base/feedback/index.tsx` |
| 1.6 | Duplicate `<Provider>` and `/notifications` route removed; unused auth/alert slices removed; the builder reads API errors through the shared parser | `src/App.tsx`, `src/redux/*`, `src/templateBuilder/builder/index.tsx` |

**Verified:**
- `tsc -b` is clean.
- ESLint reports no new findings; the 7 remaining are pre-existing, in files Phases 2–3 rewrite.
- The Vite build succeeds. The bundle is 5 MB, to be code-split in Phase 9.
- Through the Vite proxy: login (token + session cookie), `/me` with the bearer or the cookie alone, the error envelope on a bad password, logout, and deep links serving the SPA.

**Manual browser check for the team:**
1. Open http://localhost:5173 and log in as `r.kumar`: there is no admin nav, and the header shows "Ravi Kumar / Quality Approver".
2. Log in as `admin`: the admin nav is visible.
3. Reload: you stay signed in.
4. Log out: you return to the login page, and `/` redirects to login.

### Phase 2 — Templates: authoring, release, resources ✅ (2026-10-22)

**Backend**

| Step | Change | Files |
|---|---|---|
| 2.4 (B8/B9) | `to_fields` understands the builder: rich-text labels flattened; limits read from items; Dropdown/Radio options kept; **Table / Grid → one field per row × recorded column**, with row limits (number) or `OK` as the conforming value (dropdown). Every field gets a **`layout_key`** (`field_name`, or `field_name:row:column`). `problems()` flags a table with no recorded column or no rows | `app/services/form_layout.py` |
| 2.4 | `layout_key` column on `format_fields` and `record_field_values` (auto-migration on boot). It is copied to records and new revisions, `PUT /records/{id}/values` matches on it, and it is returned in format and record JSON. Record values now also return `options`, `required` and `help_text` | `app/models_qms.py`, `app/utils/schema_migrations.py`, `app/services/format_service.py`, `app/services/record_service.py`, `app/routers/records.py`, `app/routers/formats.py` |
| — | **New finding, fixed:** a non-admin reviewer of a pending template review got 404 on the draft they were asked to approve. They can now open it | `app/routers/formats.py` (`_is_pending_reviewer`) |
| — | Tests for all of the above | `tests/test_builder_layout_fields.py` (5 tests) |

**Frontend**

| Step | Change | Files |
|---|---|---|
| 2.1 | Template Builder list from `GET /api/formats/?tab=all`: tabs, tile counts, search, Code/Status columns; New Template / Upload File open the designer | `src/templateBuilder/index.tsx`, `Column.tsx` |
| 2.2 (B11) | Designer **Process & responsibilities** panel: frequency, PO, OPO, CFT members, CFT target days, QMS Coordinator, work instruction, filing folder (with "records will be filed in…" preview). Blank roles are allowed and chosen at submission | `src/templateBuilder/builder/ResponsibilitiesPanel.tsx` |
| 2.3 (B7) | **Readings & specification limits** panel (min / max / unit, or a conforming value) for every recorded item; **Table / Grid v2**: printed vs recorded columns, typed row text, per-row limits, change events | `LimitsPanel.tsx`, `TableGrid.tsx`, `layoutUtils.ts` |
| 2.5 | **Send for approval** dialog (ordered steps, reviewers, any/all, due days, priority) and **Publish without approval** (confirm). The readiness list blocks sending; `alert`/`confirm` replaced by toasts and dialogs | `SubmitApprovalDialog.tsx`, `builder/index.tsx` |
| 2.6 | Template detail page from the API: summary, responsibilities, blank or field preview, review timeline, revisions; Approve / Reject for reviewers; Edit / Discard draft / Withdraw for admins. **Route opened to non-admin reviewers** | `src/templateBuilder/BuilderTemplateDetail.tsx`, `src/App.tsx` |
| 2.7 | **Template approvals** tab in My Approvals (`/api/formats/approvals/mine`) | `src/myApprovals/TemplateApprovals.tsx`, `index.tsx` |
| 2.8 (B10) | Resources Library: released formats by folder; admin **Create Folder → `POST /api/formats/folders`** (the junk-format hack is gone); blank preview via authed blob. **File** resumes this period's draft, asks before duplicating a submitted record, and is disabled for people who may not call the format. **Change Request** opens a DCR dialog | `src/resources/ResourceDashboad.tsx`, `src/changeRequest/RaiseDcrDialog.tsx`, `src/utils/formatMapper.ts` |
| 2.9 | Template Repository from `GET /api/formats/repository`: folder tree + Unfiled, real revision history, blank preview; "Create New Version" raises a DCR | `src/templateRepo/index.tsx`, `TemplateDetail.tsx` |
| 2.10 | Attach / replace / view the blank form in the designer | `builder/index.tsx` |
| — | Folder tree actions are opt-in (`actions` prop): no more rename/delete menus that saved nothing | `src/resources/CustomFolderTree.tsx` |
| — | API modules `formats.api.ts`, `records.api.ts` (call format), `changeRequests.api.ts` (raise DCR); the old Redux folder slices / service map / thunks were removed | `src/api/*`, `src/redux/store.ts` |

**Verified:**
- `pytest`: **209 passed** (204 + 5 new).
- The `layout_key` migration re-adds the columns on an existing database.
- `scripts/check_frontend_contract.py` through the Vite proxy: **21/21**. It covers folders, a designed draft with limits and a table, the non-admin release review, Resources, callable, filing a record (values carry layout keys), the repository and a DCR.
- `tsc -b` is clean; ESLint reports no new findings; the Vite build succeeds.

**Manual browser check for the team:**
1. As `admin`, go to Template Builder → New Template. Fill the details and responsibilities, drop a Number input and a Table / Grid onto the canvas, set limits, then Save draft and Send for approval to Mohammed Shaikh.
2. As `m.shaikh`, go to My Documents → Approvals → Template approvals → Approve.
3. As `r.kumar`, go to Resources → select the template → File. This opens `/my-forms/{id}`, which is still mock until Phase 3.

### Phase 3 — Fill & submit records ✅ (2026-10-22)

**Frontend**

| Step | Change | Files |
|---|---|---|
| 3.1 | Resources **File** → call / resume (done in Phase 2) | — |
| 3.2 | Fill page from `GET /api/records/{id}`. Mode A is a generic form from `values[]`, used by every format, including the seeded ones. **Live OK / N-OK** while typing mirrors the backend's `evaluate()`; the server's verdict replaces it on save. Remark box for out-of-spec readings. **Debounced auto-save** keeps typing that happens during a save. Also: N-OK, re-verification and submitted banners; work-instruction card; Record / Track status tabs | `src/myForms/FormDetails.tsx`, `ValueField.tsx`, `recordValue.ts`, `recordStyles.ts` |
| 3.3 | Mode B, **our own controlled layout renderer**: headers and text printed; inputs matched by `layout_key`; Table / Grid with printed cells, recorded inputs and row limits; builder multi-column rows; unplaced values listed under "Other entries". The raw `fetch` in `FormFillRenderer.tsx` is no longer on any route | `src/myForms/RecordForm.tsx` |
| 3.4 | Evidence card: attach / replace the scanned hard copy (it becomes the record's document); supporting files with caption, open (authed blob), remove | `src/myForms/RecordEvidence.tsx`, `src/utils/openAuthedFile.ts` |
| 3.5 (D5) | **Confirm approvers** page: the record's fixed route with people pickers for PO / OPO / CFT (pre-selected from the format, required where the format leaves them blank), and a plain-language summary (N-OK flag, filing folder). Submits `approval_overrides`. The free-form steps, Priority card, "share without approval" and "copy" are removed | `src/myForms/ApprovalSetupPage.tsx`, `ApprovalDialogs.tsx` |
| 3.6 | My Documents from `GET /api/records/documents-listing`: **tracking colour column**; status with who it is waiting on; last approval; tab counts; department filter; debounced server-side search; server pagination | `src/myForms/MyFormsDash.tsx`, `src/base/aggrid/Column.tsx`, `src/hooks/useDebouncedValue.ts` |
| 3.7 | Track status from the record + `GET /api/workflow/{id}`: summary (tracking colour, stage, assigned to, due dates, CFT target, filing folder, N-OK / objection) and a timeline of the live chain. Before submission it previews the route | `src/myForms/TrackStatus.tsx`, `src/api/workflow.api.ts` |
| — | `records.api.ts` (record, listing, values with cache upsert, attachments, scan, submit) and `formatPeople`. Mock arrays `templateRows`, `approvalSteps` and `approvalSummary` and the hard-coded `InspectionTable` / `FormCard` were deleted | `src/api/*`, `src/constants/data.ts` |

**Backend**

| Change | Files |
|---|---|
| **Found and fixed:** a format with no Process Owner could be called and submitted but **not filled**. `can.amend`, which gates saving readings, allowed only the format's PO, while `can.fill` / `can.submit` also allowed the person who called it. While filling, saving now follows the fill rule; re-verification corrections stay with the PO. The rest of this issue is logged as **B15** | `app/routers/records.py` |
| Regression test | `tests/test_builder_layout_fields.py` |

**Also aligned:** the fill screen's `*` marks what the backend counts as required (anything with a specification, `missing_required`), not the field's `required` flag.

**Verified:**
- `scripts/check_frontend_contract.py` through the Vite proxy: **46/46** (Phases 2 + 3). Covers:
  - readings by layout key (a table cell over its row limit is N-OK, remarks kept, the blank-required list);
  - attachment upload / open / list / remove;
  - a scan becoming the record's document;
  - approver pickers;
  - submit with overrides: PO step current with the chosen person, N-OK flag and notification to the OPO, high priority, red tracking, listed under On Verification;
  - a format with blank roles: refused without approvers, accepted with them.
- `tsc -b` is clean; ESLint reports no new findings; the Vite build succeeds.

**Manual browser check for the team:**
1. As `r.kumar`, open My Documents → Draft → the yellow record.
2. Type an out-of-range bore diameter (e.g. 25.4): it turns N-OK at once and the save state updates.
3. Attach a photo, then Set up Approval → Start Approval.
4. Track status shows the chain with Ravi Kumar on step 1.

### Phase 4 — The approval chain ✅ (2026-10-23)

**Backend**

| Change | Files |
|---|---|
| **B15 fixed:** one set of helpers resolves each record's effective Process Owner / Overall Process Owner (the people chosen at submission, else the format's). They are used by `can{}` and by every record act: return for correction, send back, close the N-OK flag, file. The N-OK flag goes to, and the notifications reach, those people | `app/services/record_service.py` (`process_owner_ids`, `overall_process_owner_ids`, …), `app/routers/records.py` |
| Tests: the chosen OPO is flagged and alone clears the flag; the chosen PO returns and sends back; only the chosen OPO files | `tests/test_chosen_approvers.py` (2 tests) |

**Frontend**

| Step | Change | Files |
|---|---|---|
| 4.1 | **My Approvals** from `GET /api/my-approvals`: Overdue / Pending / Returned / Template approvals tabs with server counts; task-stat tiles (`/api/workflow/tasks/stats`); department filter; debounced search; paging. Returned items open the fill page, the rest the review page. The status filter, which the API does not support, was removed | `src/myApprovals/index.tsx`, `Columns.tsx`, `src/api/approvals.api.ts` |
| 4.2 | **Review page** `/my-approvals/:recordId`: N-OK / objection / re-verify alert, summary, **readings table with spec and OK/N-OK**, stamped PDF preview (`/api/signatures/{wf}/preview`, falling back to the document), approval details and live timeline (signatures, objections, who is outstanding) | `src/myApprovals/ApprovalReview.tsx` |
| 4.3 | **Signature pad**: draw with finger / pen / mouse, sized for the screen's pixel ratio, or type a name; sends a PNG data URL with name and designation | `src/base/signature/SignaturePad.tsx` |
| 4.4–4.5 | One decision dialog; the actions are labelled for each step: **Approve / Return for correction** (PO, OPO), **Agree / Object** (CFT), **Approve / Send back to CFT** (final). All go through `POST /api/workflow/{wf}/steps/{step}/decide`; the server maps the negative answer onto the process | `ActionDialogs.tsx`, `src/api/workflow.api.ts` (`decideStep`) |
| 4.6 | **Clear N-OK flag** (note required) and **File record** for the OPO | `ApprovalReview.tsx`, `records.api.ts` (`clearNok`, `storeRecord`) |
| 4.7 | Buttons come only from `step.can_act` and `record.can{}`; `blocked_reason` is shown when it is someone else's turn. A decision invalidates the record, workflow, lists, approvals, notifications and stats | — |
| — | Mocks `approvalRows`, `approvalDetails`, `documentMeta`, `reviewSteps`, `summaryLeft` and `summaryRight` were deleted | `src/constants/data.ts` |

**Verified:**
- `scripts/check_frontend_contract.py` through the Vite proxy: **75/75**. The full chain ran:
  - PO approval without a signature is refused, then approved signed;
  - OPO clears the N-OK flag and approves signed; the CFT opens with a target date;
  - one CFT member objects (carried on the record) and one agrees, so the record goes to the final decision;
  - the final decision sends it back, so it turns red with `reverify_count = 1`;
  - CFT agrees again, the final approval is signed, and the workflow is approved;
  - only the OPO is offered File; the record is filed in its date folder;
  - the stamped PDF carries ≥ 3 signatures;
  - a PO "return for correction" appears in the filler's Returned tab.
- `tsc -b` is clean; ESLint reports no new findings; the Vite build succeeds.

**Manual browser check for the team** (acceptance scenarios A–C in §7):
1. As `r.kumar`, go to My Documents → Approvals → Pending → the red record → Approve, signing with a finger or mouse.
2. As `s.iyer`, choose Clear N-OK flag, then Approve.
3. As `a.deshmukh`, choose Object; as `p.nair`, choose Agree.
4. As `r.kumar`, choose Send back to CFT. Then have both CFT members Agree, and as `r.kumar` Approve.
5. As `s.iyer`, choose File record.

### Phase 5 — Doc Repository ✅ (2026-10-23)

| Change | Files |
|---|---|
| Repository from `GET /api/documents/repository`. The folder tree (Records / team / format / year / month / day) has counts and pins seeded from the server. Choosing a folder includes its sub-folders. Server-side search, filed-date filter and paging | `src/docRepository/index.tsx`, `src/api/repository.api.ts` |
| **Filed-record detail:** summary, readings with OK/N-OK, signed PDF preview, open / download, approval timeline with signatures, and the full event trail | `src/docRepository/RecordFileDetail.tsx` |
| Folder tree: optional `onRename` / `onPin` callbacks saved through the API (pin for everyone, rename for admins); path ids travel as `A>B>C` because the tree joins ids with `/` | `src/resources/CustomFolderTree.tsx` |
| **BE bug found and fixed:** choosing a folder in the tree listed nothing when the format files outside `Records / …`. The tree always says `Records / …`, but the document filter compared raw paths. It now uses the same normalised `_under_folder` match as rename / pin. Regression test added | `app/services/document_repository.py`, `tests/test_repository_folders.py` |

### Phase 6 — Change Requests ✅ (2026-10-23)

| Change | Files |
|---|---|
| One page with a **Format changes (DCR) / Record changes** switch (D8). Each has status tabs, stat tiles, a "Waiting on me" toggle, a team filter, search and (RCR) paging. "New change request" raises a DCR | `src/changeRequest/index.tsx`, `Columns.tsx`, `src/api/changeRequests.api.ts` |
| **DCR detail:** Start review → Approved / Not approved (a comment is required to reject) → **Create the new revision / new format** (code, title and frequency for a new format) → open the draft in the designer | `src/changeRequest/ChnageRequestDetails.tsx` |
| **RCR detail:** Edit, Assign, Approved / Not approved, Mark implemented; open the record's document. "Request a change" was added to submitted / filed records on the fill page | same, `RaiseRcrDialog.tsx`, `src/myForms/FormDetails.tsx` |
| Raise DCR: choose a released format, or ask for a **new format** for a team. **Found and fixed (FE):** a new-format DCR had no QMS Coordinator, so nobody but an admin could decide it. The raiser now names one | `src/changeRequest/RaiseDcrDialog.tsx` |
| BE: raising / implementing an RCR honours the Process Owner chosen at submission (B15 helpers) | `app/services/record_change_request_service.py` |

### Phase 7 — People, teams, roles, departments ✅ (2026-10-23)

| Change | Files |
|---|---|
| Four tabs on the real API. **Teams:** cards with members, plus create / edit / retire / restore. **People:** grid with add (role, department, quality team) and edit (details, team, department, role, active, password reset), plus delete. **Roles:** the 4 capabilities as checkboxes; create / edit / delete; members per role. **Departments:** add / delete | `src/peopleAndTeams/*`, `src/api/admin.api.ts`, `src/base/card/TeamCards.tsx` |
| The role dialog states the B14 caveat ("Approval also lets the holder file any record") | `src/peopleAndTeams/PeopleDialog.tsx` |

### Phase 8 — Dashboard, notifications, activity log, settings ✅ (2026-10-23)

| Change | Files |
|---|---|
| **Dashboard:** real greeting; KPIs (records with filed count and % within spec, pending approvals with overdue, open DCR + RCR with "waiting on you", active templates); chart from the trend buckets (D7); Action Required from My Approvals; Recent Activity from the audit trail; 7 / 30 / 90-day range | `src/dashboard/*`, `src/api/dashboard.api.ts` |
| **Notifications:** bell badge with live unread count (polled every 60 s, on focus, and after every action); popup with the latest five; page with type / time / unread filters, search, details with email delivery status, Open (a link per notification type), mark one / all read | `src/header/*`, `src/api/notifications.api.ts`, `src/redux/store.ts` (`setupListeners`) |
| Email links resolve: `/track?record=` → Track status, `/records/new?format=` → Resources with that format selected | `src/layout/LegacyLinks.tsx`, `src/resources/ResourceDashboad.tsx` |
| **Activity Log** from `GET /api/audit`: server paging, module filter, date range, search | `src/activityLog/*`, `src/api/audit.api.ts` |
| **Settings:** profile from `/me` (read-only: only admins edit people), change password, notification toggles and appearance saved on this device | `src/header/Settings.tsx` |

### Phase 9 — Hardening & release ✅ (2026-10-23)

| Step | Result |
|---|---|
| 9.1 Access-control matrix (scenario E) | In the contract suite: a CFT member is neither offered nor allowed the PO step; non-admins cannot author templates, browse the repository or read the outbox; an unreleased draft is hidden from people not reviewing it; bad / missing token → 401 |
| 9.2 PostgreSQL | No PostgreSQL or Docker on the development machine. **Added a `postgres-e2e` CI job:** it starts a `postgres:16` service, initialises and seeds the database, runs the API, and runs `validate_workflow.py` and `check_frontend_contract.py` against it. Deploy now `needs: [test, postgres-e2e]` (`BE/.github/workflows/deploy.yaml`) |
| 9.3 Mock clean-up | All mock modules deleted (`constants/data.ts`, `docRepository/data.ts`, `templateBuilder/data.ts`), plus the unused `ReactFormGenerator` fill path (`FormFillRenderer`, `FillApp`, `fill-main`). `constants/types.ts` is pruned to the 7 types still in use. No `console.log` left |
| 9.4 Quality gates | `tsc -b` clean · **ESLint 0 findings**, including the pre-existing ones · Vite build clean, no warnings · `pytest` 213 passed · contract suite **144/144** |
| 9.5 Production config | Checklist in README → "Deploying" |
| 9.6 Bundle | Routes are lazy-loaded: the entry chunk went from ~5 MB to ~320 kB. The form designer, charts and grids load only on their screens |

**Final verification:**
- `scripts/check_frontend_contract.py`: **144/144**, both through the Vite proxy (:5173) and directly against the API (:8000).
- `scripts/validate_workflow.py`: 106/106.
- `pytest`: **213 passed**.

### Browser testing (Playwright) ✅ (2026-10-23)

The screens themselves are driven in headless Chromium (`FE/harman-paperless-factoryFE-main/e2e/`, `npm run test:e2e`, servers on :8000 and :5173). Every test also fails on any uncaught page error, console error or HTTP 5xx.

| Suite | What it drives |
|---|---|
| `01-smoke` | Every screen for admin, r.kumar, s.iyer, p.nair and m.shaikh: content, header title, settles; admin screens hidden and guarded; logout; wrong password |
| `02-record-process` | Fill (live OK / N-OK, remark, auto-save, attachment) → confirm approvers → PO approves and signs (stamped PDF preview) → OPO clears N-OK and approves → CFT object / agree → final "send back" → CFT re-agrees → final approve → OPO files → Doc Repository |
| `03-templates` | (Phase 10, §13) Document create: palette → Field Properties (label, limits, Required) → Table / Grid cells (printed text, number limits) → Save Draft → Create Template (title, code, team, folder) → Continue (responsibilities) → send for approval → m.shaikh releases it → r.kumar fills the table, judged per cell. **Upload File**: the IFC check sheet (Excel) saved as a template; the change-request **PDF read with OCR** into the designer |
| `04-change-requests` | New-format DCR raised → reviewed → approved → executed into a draft → opened in the designer; a change DCR raised from Resources is refused when one is already open, then turned down; RCR raised on a record → approved → implemented |
| `05-admin` | Department, role, team, person (who then signs in); edit; team members; retire; delete |
| `06-dashboard-notifications-log` | Dashboard figures and range; bell popup; one notification of every kind opens a working screen; filters, mark read, mark all read; Activity Log module filter and search |

**Result on a freshly seeded database: 31/31.** Bugs the browser found, all fixed:

| Bug | Fix |
|---|---|
| Header title showed "Resources" on most screens | `metaFor()`: longest path-prefix match (`constants/pageMeta.ts`) |
| Template designer unstyled; its icons were empty squares | Scoped Bootstrap-like styles (`builder/designer.css`); Font Awesome added; the global `* { font-family: Geologica !important }` overridden for icon classes |
| Adding a Table / Grid crashed the whole app | The registry held a JSX element instead of the component |
| Reopening a saved template with a Table / Grid crashed the app | react-form-builder2 writes into layout items; RTK Query data is frozen → the designer gets a `structuredClone` |
| A crash in one screen blanked the whole app | `ScreenErrorBoundary` around the page in `MainLayout` (sidebar and header stay) |
| **A limit of 0 was saved as "no limit"** (e.g. run-out 0 – 0.05 mm) | BE `form_layout._number`: `0 in (None, "", False)` is true in Python; regression test added |
| "Request a change" offered on records the person may not change (→ 403) | Record JSON gains `can.request_change` (the RCR service's own rule); the button follows it |
| AG Charts console error on the dashboard (update of a torn-down chart) | Chart data memoised; each data set gets a fresh chart instead of an in-place update |
| Dialog text areas had no accessible name | `CustomTextArea` sets `aria-label` |
| Long team codes spilled out of the avatar; "1 members" | Avatar scales its type and clips; singular label |
| Table / Grid column controls squeezed in narrow columns | Controls wrap |
| Timeline read "role in person"; "Spec: -" for entries with no limit | Wording fixed; "-" treated as no limit |

After the fixes: `pytest` **214 passed**, `validate_workflow.py` 106/106, contract suite 144/144, `tsc -b` clean, ESLint 0, build clean.

---

## 12. Open items after integration

Every screen now runs on the API. These remain, by decision or because they need something the team must supply:

| Item | What | Who |
|---|---|---|
| **D11 / B14** | The capability model is coarser than the QMS rules: "Approval" also lets the holder file any record, and "Fill records" lets them fill any format. The seed avoids it with a narrower role; roles created in the UI do not. Recommended: split supervisor capabilities from approval in `PERMISSION_CATALOG` | PO + BE |
| **B12** | Email-link approvals (`/approve/:token`) are built in the BE but never issued; emails link to Track status instead. To enable them, call `approval_link_service.issue` per step assignee, add an FE `/approve/:token` page, and make the link service UTC-aware | BE + FE |
| Reminders | No scheduler: CFT-overdue / step-SLA reminders are not emailed (`remind` only logs). Pending-inspection notices are raised when the dashboard is read | BE |
| RCR implement | Marks the request implemented, but does not change record data (the note records what was done) | BE |
| PostgreSQL | The `postgres-e2e` CI job must pass on the first push to `harman-dev` (it could not be run locally) | DevOps |
| Production | Set `CORS_ORIGINS`, `APP_BASE_URL` and SMTP on the server; rotate `SECRET_KEY` and the `jwt_secret_key` row (the old hard-coded token was committed) | DevOps |
| Not in scope | CAPA screens (`/api/actions`), signature placement editor, workflow escalate / cancel tools, admin settings / backup / health screens (Swagger covers them). OCR template import is now in (§13) | — |

---

## 13. Template Builder redesign and document import (Phase 10) ✅ (2026-10-23)

The Template Builder follows the Figma screens (list, *Document create*, Field Properties, Create Template), and **Upload File** reads an Excel workbook, PDF or image of a paper form into an editable template. The OCR service and the form builder library that were developed on their own (`Template_OCR/`) are now part of BE and FE; that folder is removed.

### What moved where

| From `Template_OCR/` | To | Notes |
|---|---|---|
| `ocr-backend/app/*` (format registry, Excel reader / writer, grid interpreter, OCR pipeline) | `BE/app/ocr/` | `main.py` replaced by `BE/app/routers/ocr.py` (`/api/ocr/*`, signed in; template import needs `formats.manage`, and is audited). PDF / image handlers load only when OpenCV is installed |
| `ocr-backend/requirements.txt` | `BE/requirements.txt` (Excel: openpyxl, xlrd, xlwt, xlutils, defusedxml, rapidfuzz; numpy 2.3.5) + `BE/requirements-ocr.txt` (paddlepaddle 3.1.1, paddleocr 3.7.0, opencv-contrib 4.10) | Dockerfile: `--build-arg WITH_OCR=true` |
| `ocr-backend/tests`, `samples/`, `sample/` | `BE/tests/ocr/`, `BE/tests/ocr/samples/`, `BE/tests/ocr/samples/client/` | HTTP tests run against the router on a bare app (`tests/ocr/api_app.py`). Engine tests run with `RUN_OCR_TESTS=1` |
| `react-form-builder/src`, `scss`, `types` | `FE/.../src/vendor/react-form-builder/` | Replaces the npm `react-form-builder2` (same 0.20.3 base, plus the Table element, table editor and OCR views). Its dependencies are now direct; `react-bootstrap-slider` (React 16 only) replaced by a native range input; `isomorphic-fetch` dropped |
| Figma `1.png`–`4.png` | `templateBuilder/index.tsx`, `templateBuilder/designer/` | — |

### Changes to the vendored library (marked in the source)

- `index.jsx`: exports `BuilderProvider`, `Preview`, `Toolbar`, so the page lays them out (canvas in the middle, palette in the side panel).
- `toolbar.jsx`: `layout="tiles"`, grouped collapsible sections and `iconNode` icons.
- `preview.jsx`: `editFormContainer`, which renders the edit form into the Field Properties tab; clicks inside `[data-rfb-keep-edit]` (the text toolbar) keep the field open.
- `sortable-element.jsx`: clicking an element selects it; field width (`field_width`) and alignment (`text_align`).
- `form-elements/index.jsx`: `placeholder` on text inputs; native range input.
- `table-editor.jsx`: Min / Max / Unit on a number cell, Required on any input cell.
- `stores/store.js`: `unsubscribe` (the canvas and palette unsubscribe on unmount).
- `ocr/ocr-client.js`: points at `/api/ocr` with the caller's headers.
- `myxss.js`: allows the tags the text toolbar produces.
- `UUID.js`, `stores/registry.js`: ES modules (Vite serves source as ESM).
- `scss/react-date-picker.scss`: the datepicker CSS is imported by the element.

### Decisions

| Decision | Choice |
|---|---|
| One table element | The library's **Table** (merged cells, heading rows; what OCR produces) is the designer's Table / Grid. The earlier `TableGrid` stays registered, so existing templates and records still render; it is no longer offered |
| Limits | In **Field Properties**: Min / Max / Unit for a number field, the conforming value for a choice, Min / Max / Unit per number cell in a table. The separate limits panel is gone |
| Continue | A second step (no Figma screen for it): responsibilities, the blank form, Send for approval / Publish |
| Template details | Figma's Create Template, plus **Quality team** (the backend needs one) and a suggested code (`QF-<team>-NNN`) when left blank. The chosen folder is the format's `storage_path` |
| Required entries | **The field's Required flag decides** (`record_service.missing_required`). Before, any entry with a specification was required and the flag was ignored, which would have made every ✓ / ✗ cell of a monthly check sheet compulsory |
| Table cells | A number cell with limits is required by default; a ✓ / ✗ cell is judged (✗ = N-OK) and optional unless marked Required |

### Backend

- **`form_layout.add_table`** derives one field per input cell. The label is the row's printed text, including a merged cell above that spans into the row, plus the column heading, each shortened so labels stay distinct. The key is `field_name:row.key:column.key`.
- Cell types: text, number, date; check becomes select OK / N-OK.
- **`problems()`**: a table with no input cells is reported.
- **`Checkboxes`** groups are answered as a choice.
- **`updated_at`** is in the format JSON (the list's Last Update).
- **Seed**: a template folder tree (`Teams / <team> / Procedures …`).

### Frontend

- **List (Figma 1)**: Pending Approval wording, Total Template tile, the Document Name / Department / Type / Last Update columns, and Upload File.
- **Designer (Figma 2–4)**:
  - Breadcrumb *Template builder / Document create*; the side menu folds on the designer.
  - Text toolbar: undo/redo, style, B/I/U/S, code, clear formatting, alignment, lists, code block, quote, horizontal line, zoom, Field Setting.
  - Dotted canvas and the Add Fields tiles.
  - Field Properties: Basic Setting, Option, Default Value, Validation, Appearance, Table layout.
  - Create Template with a folder tree, search and new folder.
  - Eye preview, Save Draft, Continue.
- **Upload File**: drop or browse a file, convert it (elapsed seconds shown), see what was detected over the page, then open it in the designer with Create Template pre-filled. A PDF or picture becomes the blank form.
- **Records**: the fill screen draws the Table (heading rows, merged cells, printed text, inputs by cell). It shows formatted text, placeholders, default values and field widths; the required mark follows the field.
- **App**: a screen crash stays inside the screen (`ScreenErrorBoundary`).

### Verified

- `pytest`: the whole suite, including `tests/ocr` (Excel, registry, HTTP) and `test_designer_table.py`.
- `RUN_OCR_TESTS=1 pytest tests/ocr`: **74/74** in the BE venv. That covers templates from the client's PDFs, filling from scans with handwriting drawn in, and an Excel template filled from a scan.
- Playwright `03-templates`:
  - designing from scratch: Field Properties, table cell limits, Create Template with a folder, Continue, approval, release;
  - filling a record, with N-OK judging;
  - **Upload File** with the IFC check sheet (Excel) and with the change-request **PDF read by OCR**.

### Open

| Item | What |
|---|---|
| Filling a record from a filled scan | The service already reads values from a filled copy (`/api/ocr/extract`, `/read-form`), and the library has the review view (`OcrScanFill`). Wiring it into My Documents ("Filled it on paper? Attach the scan") would pre-fill the readings |
| Save values to Excel | `/api/ocr/export` writes a record's values into the source workbook; not offered in the UI yet |
| OCR speed | CPU only: 10–40 s a page. A GPU (`OCR_DEVICE=gpu:0`) or the server models change the trade-off |
| Handwriting | Read with lower accuracy than print; every value carries a confidence and is reviewed before it is used |

## 14. End-to-end run with the client's samples (24 Oct 2026)

Three documents from `sample/`, one of each kind, taken through the whole process on the dev database (`BE/data/documents.db`, **not** reset, so every step can be inspected):

| Sample | Template | People | Record | Filed in |
|---|---|---|---|---|
| `IFC Check Sheet.jpg` (OCR) | QF-PQ-002 rev 00 Daily → **rev 01 Monthly** after DCR-2026-0002 | PO Ravi Kumar, OPO Sunita Iyer | REC-QF-PQ-002-20261024-01 (N-OK cleared by the OPO) | Teams / Process Quality / Inspection Logs / QF-PQ-002 / 2026 / 10-Oct / 24 |
| `HPU-F-MR-04 … Change Request.pdf` (OCR) | QF-SQ-003, Per event | PO Kavitha Reddy, OPO Deepak Varma | REC-QF-SQ-003-20261024-01, then RCR-2026-0001 (raised, approved, implemented) | Teams / Supplier Quality / Incoming Inspection / QF-SQ-003 / 2026 / 10-Oct |
| `Daily check sheet.xlsx` (Excel) | QF-PQ-003, Monthly; ✓ / ✗ cells and lux readings limited to 800–1200 lux | PO Aryan Sharma, OPO Sunita Iyer | REC-QF-PQ-003-20261024-01 (760 lux at Sta.3 → N-OK, cleared) | Teams / Process Quality / Inspection Logs / QF-PQ-003 / 2026 / 10-Oct |

QMS Coordinator Mohammed Shaikh released every template; CFT Priya Nair and Anil Deshmukh agreed every record.

### Fixed on the way

| Area | Problem | Fix |
|---|---|---|
| OCR | Day numbers misread ("1 2 3 … 2l"); the title was the company name | `ocr/headings.py` renumbers a run of headings; `ocr/title.py` picks the form's title |
| OCR | A borderless revision history read as a jumble of labels | `ocr/textgrid.py`: text set out in columns becomes a printed **reference** table (`reference: true`, exempt from "the table records nothing") — scans, PDFs and Excel alike |
| OCR | Two boxes both labelled "Sign"; "NEW" without its row; "Approved By: (M.R.)" | `ocr/labels.py` names a repeated label after the field above it; a row label carries across its sub-labels; a colon before a qualifier is dropped |
| OCR | A Paddle error was a 500 | one engine thread, one retry, then a 503 with a reason (`ocr/engine.py`) |
| Templates | A suggested code could collide | the server assigns the team's next code when it is left blank (`GET /api/formats/next-code`) |
| Templates | Fields in a row's columns came after every table | `form_layout.reading_order`; `scripts/sync_format_fields.py` re-orders saved templates |
| Templates | A table cell with limits was required, so a monthly sheet listed every day to come as missing | a table cell is required only when marked so (the same script updates saved templates) |
| Designer | A field in a row could not be selected by clicking it; columns overlapped | fields in columns select on click; border-box sizing; the row's buttons have their own strip |
| Designer | Limits had to be typed into each of 31 day cells | table editor: **Limits to row / … to column**; the large table editor for wide sheets |
| Records | A JPG hard copy could not carry signatures | a picture is kept as a PDF (`evidence_service`; `scripts/convert_image_evidence.py` for older ones); a hard copy must be a PDF or picture |
| Records | An 817-cell sheet took 27 s to open | `ValueCell` (native inputs); 1–4 s |
| Records | Periods, folders and record numbers were cut on UTC days | the plant's calendar (IST) via `utils/ist.py`; stored times stay UTC |
| Filing | Two templates in one library folder shared their date folders | each template files under its own code folder |
| Repository | A record's own history (filed, change requests) was not shown | the trail merges the record's events with the approval's |
| Links | DCR emails linked to `/change-requests?id=` (no such screen); unknown links were a blank page | the email links to the request; old links redirect; a "page does not exist" screen |
| Links | A link to a superseded revision said only "Format not found" | it says the revision was replaced and where the current one is (historical revisions stay admin-only) |

### Notes on the data

- REC-QF-PQ-002-20261024-01 also holds two ticks on days 4 and 10 and three on days 21–22, entered by the scripts that measured the fill screen; they were approved with the record.
- REC-QF-SQ-003-20261024-01 was raised before periods followed IST: its period reads "24 Oct 2026 12:10" (UTC). Filed records are not rewritten.
