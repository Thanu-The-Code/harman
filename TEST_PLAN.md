# Paperless Factory — Acceptance Test Plan and Report

Release candidate of 24 Oct 2026. Scope: the whole product as the client will receive it — FastAPI backend (`BE/`), React frontend (`FE/harman-paperless-factoryFE-main/`), the OCR / Excel import, and the QMS record process.

## 1. How it is tested

| Track | Who | Environment | What |
|---|---|---|---|
| A. Template Builder × 9 files | lead | main stack (`:8000` / `:5173`) | every client sample in every format it came in |
| B. Roles and processes | test agent | isolated stack (`:8002` / `:5175`, copy of the DB) | every role does every activity, end to end, through the UI |
| C. Exceptions, security, robustness | test agent | isolated stack (`:8003` / `:5176`, copy of the DB) | wrong input, wrong person, wrong order, broken files, stale links |
| D. Regression | lead | isolated stack | BE pytest, OCR corpus, workflow acceptance, FE contract, Playwright e2e, build |

Every defect found is reproduced, fixed at its cause, covered by a test where the code allows, and re-verified through the UI. Test data is never cleaned out of the main database.

## 2. Track A — Template Builder with every sample

The nine client files: three forms, each as JPG, PDF and Excel.

| Form | JPG | PDF | Excel |
|---|---|---|---|
| IFC Check Sheet (monthly, 38 columns, ✓ / ✗) | A1 | A2 | A3 |
| HPU-F-MR-04 Document Creation / Change Request | A4 | A5 | A6 (`.xls`) |
| Daily check sheet (shift × day grid, lux readings) | A7 | A8 | A9 |

For each file:

1. **Import**: Upload File → Convert; time taken, what was detected, no error.
2. **Structure** against the paper form: title, header fields, every table (columns, heading rows, merged cells, printed vs input cells), row/column fields, signatures, footer / revision history, logo.
3. **Same form, three formats**: the JPG, PDF and Excel imports of one form give the same tables and field labels (differences listed and justified).
4. **Editable**: select every kind of element (top level, inside a row column, table); edit label / required / width / placeholder; add, delete and reorder fields; undo / redo; table editor (cell type, limits, merge / split, add / delete row and column, apply to row / column / all); preview.
5. **Save and reopen**: Save Draft, reload, everything as it was; readiness messages make sense.
6. **Representation**: the fill screen, the review screen, the Doc Repository and the signed PDF show the same structure.

## 3. Track B — Roles and processes

Roles: Administrator, QMS Coordinator (m.shaikh), Process Owner (r.kumar, a.sharma, k.reddy), Overall Process Owner (s.iyer, d.varma), Quality CFT (p.nair, a.deshmukh), and a person outside the process.

- **Administrator**: people, teams, roles, departments; template authoring; template repository; settings; activity log.
- **Template lifecycle**: draft → send for approval → *returned for changes* → revise → approve → release; withdraw a draft.
- **Records**: call from Resources; fill (digital and hard copy); auto-save; required entries; N-OK; submit; PO approve / return; OPO clear N-OK; CFT agree / object; final decision approve / send back; reverify loop; filing; Doc Repository; signed PDF.
- **Change**: DCR for a new format, DCR for a change (approve, reject, execute, new revision released, old superseded), RCR (raise, assign, decide, implement).
- **Everyone**: dashboard figures, notifications (bell, page, mark read, every link), activity log, search and filters, logout / session.

## 4. Track C — Exceptions, security, robustness

- **Input**: empty, oversized, corrupt, wrong-type and duplicate files; very long text; special characters / unicode; numbers out of range; dates; HTML / script in labels.
- **Authorisation**: every action attempted by the wrong role, through the UI and directly against the API; URL tampering; another team's records.
- **Order of operations**: double submit, double approve, acting on a superseded revision, editing a released template, filing twice, deleting what is in use.
- **Sessions**: expired / tampered token, logout in one tab, back button after logout.
- **Resilience**: API down while filling, slow responses, rate limit, unknown routes and ids, page reloads mid-flow.
- **Errors are humane**: every refusal says what to do, no raw stack traces, no blank screens, nothing lost.

## 5. Track D — Regression gates

| Gate | Command | Pass mark |
|---|---|---|
| BE unit / API | `pytest tests` | all |
| OCR corpus | `RUN_OCR_TESTS=1 pytest tests/ocr` | all |
| Process acceptance | `scripts/validate_workflow.py --url <isolated>` | all checks |
| FE contract | `scripts/check_frontend_contract.py <isolated FE>` | all checks |
| UI end to end | `npx playwright test` (`E2E_BASE_URL=<isolated FE>`) | all |
| FE build | `tsc -b`, `eslint .`, `vite build` | clean |

## 6. Results (24 Oct 2026)

All tracks ran. Every defect below marked fixed was reproduced, fixed at its cause, covered by an automated test where the code allows, and re-checked in the browser or by re-running the finder's own script.

### 6.1 Gates — final run

| Gate | Result |
|---|---|
| BE `pytest tests` | **318 passed** (24 OCR-engine tests skipped here, run below) |
| OCR corpus `RUN_OCR_TESTS=1 pytest tests/ocr` | **90 passed** |
| Process acceptance `validate_workflow.py` | **106 / 106** |
| FE contract `check_frontend_contract.py` | **144 / 144** |
| Playwright e2e (`e2e/`, 33 scenarios) | **33 / 33** |
| FE `tsc -b`, `eslint .`, `vite build` | clean |
| Docker images | not built: Docker is not installed on the test machine |

### 6.2 Track A — Template Builder with all nine files

| File | Convert | Elements | Fields | Tables | Saved / reloaded / preview |
|---|---|---|---|---|---|
| IFC Check Sheet .jpg / .pdf / .xlsx | 11.7 s / 12.7 s / 0.5 s | 9 | 817 / 817 / 791 | 1 (38 columns, days 1–31) | ✓ ✓ ✓ |
| Change Request .jpg / .pdf / .xls | 3.5 s / 4 s / 0.2 s | 26 | 57 / 57 / 57 | 3 (+ printed revision history) | ✓ ✓ ✓ |
| Daily check sheet .jpg / .pdf / .xlsx | 10.7 s / 7.1 s / 0.4 s | 14 / 14 / 12 | 501 / 501 / 501 | 1 (35 columns, shift × day) | ✓ ✓ ✓ |

Each form now gives the same structure whichever way it arrives. The one difference (IFC: 791 cells in the workbook) is in the sources: the printed sheet has a "Vendor / MSIL" row the workbook does not.

In the designer, every element was selectable, nothing spilled out of its column, and every kind of edit was saved and still there after a reload:
- label, required, delete, undo / redo;
- a field added from the palette, with limits;
- table rows and columns added and removed, cell types, limits per row.

Fixed on the way:
- an Excel label that runs over its empty neighbour is one label (no phantom "Requester Sign (2)");
- "Revision Number OLD / NEW" keep their row name, in reading and writing workbooks too;
- a row made only of merged cells is dropped;
- the form's title becomes its heading;
- fields on one printed line share a row;
- ✓ / ✗ legends read as marks;
- placeholder texts in the properties panel say what they are for.

### 6.3 Track B — every role, every activity (test agent)

Covered for every role, through the real UI:
- **People & Teams:** departments, roles, teams and people added, edited and removed; a new person signs in.
- **Template lifecycle:** import, design, send for approval, reject, revise, release, discard a draft.
- **PQ and SQ records:** every branch — return, N-OK, CFT objection, send back, re-verify, file — then the Doc Repository.
- **Change requests:** a DCR for a new format and for a change (rejected, then executed and the new revision released); RCRs.
- **Everyday screens:** dashboard, notifications (every kind of link, for all 9 people), searches, filters, sign-out.

Speed: every screen opened in 1.1–2.7 s.

Fixed:
- **Notifications:**
  - per-event formats flooded their owner with "inspection pending" (73 in an hour);
  - the author was never told of a template decision;
  - the N-OK owner got two messages for one event.
- **Dashboard:**
  - it ignored its date range;
  - overdue approvals were missing from "Action Required" and from My Approvals' Pending list;
  - the pass rate counted records with nothing to judge.
- **Doc Repository:**
  - Download gave the unsigned scan (now the signed PDF, named by record number);
  - the trail lost the first round after a return;
  - the summary did not show the revision.
- **Records:**
  - a returned record was labelled "reverify with CFT" and did not show why it was returned;
  - red stayed after re-verification;
  - blank required entries are now shown on the set-up and review pages (they warn, as process B3 requires, and do not block);
  - the hard-copy button was offered when it could not be used.
- **Navigation and messages:**
  - My Approvals was missing from the sidebar;
  - Resources search only looked in the open folder;
  - refused screens dropped people on the dashboard without a word;
  - not-found pages offered a pointless retry;
  - a deactivated person was told the password was wrong.
- **Templates and change requests:**
  - template-review status chips, Builder counts and naming;
  - DCR "Implemented" relabelled "Executed";
  - a new format's code is assigned when left blank;
  - a template naming no Process Owner was offered to other teams' people (now only to its own team).
- **Settings:**
  - it had switches and a dark mode that did nothing (replaced by an honest description).
- **Activity Log and layout:**
  - the Activity Log showed raw action names and ids, and everybody's sign-ins and IP addresses;
  - the header showed "Quality Approver" for everybody (now the job title);
  - another person's drafts showed in My Documents;
  - layout clipping in the Doc Repository and Resources, and a blank page-size box.

### 6.4 Track C — exceptions, authorisation, robustness (test agent)

| Severity | Found and fixed |
|---|---|
| Blocker | One person could name themselves Process Owner, Overall Process Owner and CFT, and approve and file alone → approvers are validated (active, in the team, allowed to sign / approve) and the four-eyes rule is enforced, at submission and in template readiness |
| Blocker | Submitting with another record's document cancelled that record's approval → only the record's own (or an unused) document is accepted |
| Blocker | Attachments were served back as web pages (stored XSS) → type decided by the server, `nosniff`, sandboxed; also document and blank-form downloads |
| Major | Empty, renamed, password-protected or unreadable "PDF" hard copies were accepted and broke signing → content checked before anything is stored |
| Major | Creating a user without a department crashed (500) |
| Major | Weak and empty passwords accepted; no username / email rules → one policy everywhere |
| Major | Signing out or changing a password left the token working → tokens are revoked (sign-out: that one; password change, reset or deactivation: all) |
| Major | A new-format DCR could name its raiser as coordinator; an RCR raiser could assign and approve their own; double clicks executed one DCR three times → four eyes, and status changes made atomic |
| Major | Signature name and title came from the browser; every signer's signature image was readable by anyone → taken from the account; images only to their signer and administrators |
| Major | A cancelled or escalated record approval could strand or leave the team → refused for records; escalation stays in the team and away from other role holders |
| Minor | 400 for "wrong person" (now 403); a non-JSON body crashed the validation handler, which also logged request bodies (passwords); readiness probe failed on a removed setting; heavy OCR endpoints open to everyone; "NaN" passed every limit, "Infinity" crashed |
| Hardening | Sign-in required by default (fail closed); API docs hidden in production; standard security headers on the API and in the nginx image |

Also checked in the browser:
- every unknown link shows a clear message;
- a failed save keeps what was typed and says so;
- an expired sign-in brings the person back to the same screen after signing in;
- a double-clicked Start Approval sends once;
- slow screens show that they are loading.

### 6.5 Decisions for the client (behaviour as designed, to be confirmed)

- **Visibility:** every signed-in person can read every team's filed records and signed PDFs (the Doc Repository is plant-wide). Team-only reading would be a change of scope.
- **Blank required entries** warn and do not block (process B3: an incomplete record still goes to approval, its blanks named).
- **The Overall Process Owner** may approve before clearing an N-OK; filing is what is blocked until it is cleared.
- **Administrators** have "Publish without approval" (recorded in the Activity Log).
- **The signed PDF of a hard-copy record** is the scan plus a signature page; the readings typed on screen are in the record, not printed into the scan.
- **Notifications** cannot be switched off: they are the process triggers. The links in emails use `APP_BASE_URL`, which must be set to the production address.

### 6.6 Known, not changed

- Legacy filing roots ("Records / …") from the demo seed sit beside "Teams / …" in the Doc Repository tree (data, not code).
- `/resources?format=` selects the format but does not expand its folder in the tree.
- Rate limiting is in memory, per server process and per IP. Behind one proxy the whole plant shares a bucket. Use a shared store (Redis) if several API processes run.
- Uploads are size-checked after they are read into memory (100 MB limit). Set the same limit on the reverse proxy.
