# Testing and demonstrating the Record Process

Two audiences, two documents in one:

- **Part 1 — Run it.** Every command, in order.
- **Part 2 — Test it yourself**, box by box against the client's flowchart.
- **Part 3 — Demonstrate it** to somebody in ten minutes.

Everything below was run end to end on a clean database before this was
written. Where a number is quoted, it was measured.

---

# Part 1 · Running it

## First time

```bash
# 1 · dependencies  (Windows; see README for Linux/Docker)
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pip install python-magic-bin==0.4.14     # libmagic DLLs, Windows only

# 2 · high-accuracy OCR  (optional, ~700 MB — see "Is OCR working?" below)
.venv\Scripts\pip install -r requirements-ocr.txt

# 3 · configuration
copy .env.example .env
#     set SECRET_KEY, and TESSERACT_PATH / POPPLER_PATH if you installed them

# 4 · database, demo data, server
.venv\Scripts\python cli.py init
.venv\Scripts\python scripts\seed_quality_records.py
.venv\Scripts\python cli.py serve
```

Open **http://127.0.0.1:8000**.

On Linux/macOS the same three commands are `python cli.py init`,
`python scripts/seed_quality_records.py`, `./run.sh`.

## Every day

```bash
.venv\Scripts\python cli.py serve            # start it
.venv\Scripts\python cli.py records          # the traffic light, from a terminal
.venv\Scripts\python cli.py change-requests  # what is waiting on the QMS Coordinator
.venv\Scripts\python cli.py ocr              # which engine reads scans
.venv\Scripts\python cli.py status           # folders, counts, AI, embeddings
.venv\Scripts\python cli.py users            # accounts
```

## Who to sign in as

Everybody the seed creates shares one demo password. It is not published here:
ask the project administrator for it.

| Sign in as | Their part in the process |
|---|---|
| `admin` | Administrator — builds and releases formats |
| `r.kumar` | **Process Owner** (Process Quality) — calls, fills, approves, decides |
| `s.iyer` | **Overall Process Owner** — second approval, N-ok flags, files records |
| `a.deshmukh` | **Quality CFT** |
| `p.nair` | **Quality CFT** |
| `m.shaikh` | **QMS Coordinator** — approves format changes |
| `k.reddy` | **Process Owner** (Supplier Quality) |

> Change these before the system reaches a real network.

## Checking it works, without a browser

```bash
# every business rule, against the running server — 106 checks
.venv\Scripts\python scripts\validate_workflow.py

# the code itself — 308 tests, about 6 minutes
.venv\Scripts\python -m pytest tests\ -q
```

Both should end green. The first one signs in as all seven people and walks the
whole flowchart; if a rule of the process has stopped holding, it names it.

## Starting over

```bash
del data\documents.db
.venv\Scripts\python cli.py init
.venv\Scripts\python scripts\seed_quality_records.py
```

## Is OCR working?

```bash
.venv\Scripts\python cli.py ocr
```

`PaddleOCR — installed: yes` means scans are read accurately **and keep their
table structure**. Without it the system still works; it falls back to
Tesseract, which reads a ruled inspection sheet as a few lines of prose and
loses most of the readings.

**The first scan after a restart takes about 25 seconds longer** — that is the
OCR models loading, once per run of the server. Every scan after it takes about
5 seconds.

---

# Part 2 · Testing it yourself, box by box

About 20 minutes. Run the seed first so there is something to look at, and keep
two browser windows open (one normal, one private) so you can be two people at
once.

Each section names the box of the client's flowchart it tests and **what to
look for** — the observation that proves the rule, not just the click.

---

### B1 · Blank formats live on the server — as `admin`

| Step | Do this | ✅ Expect |
|---|---|---|
| 1.1 | Sign in as **`admin`** → **Formats** | Three released formats, one per quality team, at three different frequencies (Daily, Weekly, Monthly) |
| 1.2 | Open **QF-PQ-001** | Four named responsibilities, the specification limits on each reading, and the exact path approved records are filed to |
| 1.3 | Try to change anything on it | **You cannot.** An active format is read-only — that is B9, and section 8 below tests it properly |
| 1.4 | Press **New format**, set a code and team, change **Filled how often** | The storage path preview underneath **changes with the frequency** |
| 1.5 | Add a reading with a min and a max, save | It appears as a **draft**, and **Release for use** is disabled until every responsibility and reading is set |

> **Why it matters:** the format carries the four people and the limits, so no
> one ever builds an approval chain by hand or argues about what "in spec" means.

---

### B2 · The Process Owner calls a format — as `r.kumar`

| Step | Do this | ✅ Expect |
|---|---|---|
| 2.1 | Sign in as **`r.kumar`** | The menu **is** the process: Formats → Fill Record → Approvals → Tracking → Storage → Change Request |
| 2.2 | Open **Fill Record** | Only **your own** formats are offered — a CFT member sees none here |
| 2.3 | Look at a format card | It names the period it is for, and **warns if that period already has a record** |
| 2.4 | Press **Fill it here** on QF-PQ-001 | A record is raised with a number like `REC-QF-PQ-001-20260902-01`, status 🟡 **yellow** |

---

### B3 · Filling it — still `r.kumar`

| Step | Do this | ✅ Expect |
|---|---|---|
| 3.1 | Type a **Bore diameter** of `25.0` | The badge turns **ok** as you type |
| 3.2 | Change it to `26.5` | It turns **N-ok** immediately and the row is tinted red |
| 3.3 | Put it back to `25.0` | **ok** again |
| 3.4 | Leave a reading blank and try to submit | **Refused**, naming the blank reading |

#### The hard-copy route — the one worth showing

| Step | Do this | ✅ Expect |
|---|---|---|
| 3.5 | Press **Attach the scanned hard copy** and upload a photo or scan of a filled form | *(first time after a restart: ~25 s; after that ~5 s)* |
| 3.6 | Look at **"The scan appears to say"** | The readings it found, each with the label it read them from and **how confident it is** |
| 3.7 | Look at the verdict beside each | Values outside the limits are marked **"would be N-ok"** *before* you accept them |
| 3.8 | Open **"The table it recovered"** | The sheet's table, **still a table** — this is what Tesseract cannot do |
| 3.9 | Press **Use all of these** | The readings fill in above. **Check each against the paper** |

> **The rule:** OCR only ever *suggests*. Nothing reaches a record until a
> person accepts it — an engine that misreads 25.02 as 26.02 must not be able to
> put an out-of-specification value into a quality record on its own.

| Step | Do this | ✅ Expect |
|---|---|---|
| 3.10 | Press **Submit for approval** | You land on Tracking; the record is now **with the Process Owner** |
| 3.11 | Sign out, sign in as **`r.kumar`** again → **Approvals** | The record is on your task list — B3's email trigger |

---

### B4 · The Process Owner's approval — `r.kumar`

| Step | Do this | ✅ Expect |
|---|---|---|
| 4.1 | Open the task | There is **no "Reject" button.** A quality record is never rejected |
| 4.2 | Read the negative button | It says **Return for correction** — the chart approves "if found within specification condition"; if it is not, you correct it |
| 4.3 | Press **Approve & sign**, draw a signature | Approved |
| 4.4 | Sign in as **`s.iyer`** → **Approvals** | It is now waiting on the **Overall Process Owner** — B4's second email trigger |
| 4.5 | Approve and sign | It moves to the joint review |

#### Test the other outcome

| Step | Do this | ✅ Expect |
|---|---|---|
| 4.6 | On a **second** record, press **Return for correction** and give a reason | Record goes back to **filling** — *not* deleted |
| 4.7 | Correct a reading and submit again | **Same record number.** A correction never raises a second record for one period |

---

### B5 · The N-ok flag — `r.kumar`, then `s.iyer`

| Step | Do this | ✅ Expect |
|---|---|---|
| 5.1 | Raise a record and put a reading **outside its limits**, then submit | |
| 5.2 | Sign in as **`s.iyer`** → **Tracking** | The record is 🔴 **red**, with a flag addressed to you naming exactly which reading failed |
| 5.3 | Note when it arrived | The flag went out **the moment it was submitted** — it did not wait its turn in the approval queue |
| 5.4 | Take the record all the way to approved, then open **Storage** and try to file it | **Refused** until the action taken is recorded |
| 5.5 | Press **Record the action taken**, then file it | Now it files |

> **Why:** the chart raises the flag "for further action". Filing it unactioned
> would bury the exact finding the flag exists to surface.

---

### B6 · The joint review — `a.deshmukh`, then `p.nair`

| Step | Do this | ✅ Expect |
|---|---|---|
| 6.1 | Sign in as **`a.deshmukh`** → **Approvals** | The joint review, with a **target date** |
| 6.2 | Approve it, then look at **Tracking** | It has **not** moved on. The review is *joint* — one voice does not conclude it |
| 6.3 | Read who is outstanding | **Priya Nair** is named |
| 6.4 | Sign in as **`p.nair`** and approve | Now it reaches the final decision |
| 6.5 | On another record, press **Object** instead | The process **does not stop**. Your objection is recorded |
| 6.6 | As `r.kumar`, open that record | The objection is shown to whoever takes the final decision, and the record is 🔴 **red** |

> **Why:** B7's condition is *"Final Decision require from CFT"*. The CFT
> **informs** the decision; it does not take it.

---

### B7 and D1 · The final decision, and the loop — `r.kumar`

**This is the most important test in the document.**

| Step | Do this | ✅ Expect |
|---|---|---|
| 7.1 | Open a record at the final decision | |
| 7.2 | Try to send it back with **no reason** | **Refused** |
| 7.3 | Press **Send back to the CFT** with a reason | |
| 7.4 | Watch what happens | Record turns 🔴 **Red — Needs to reverify with CFT** |
| 7.5 | Check the joint review | It has **reopened with both members outstanding again** — nobody's earlier approval carries over |
| 7.6 | Check the round counter | **1** |
| 7.7 | **Confirm the record still exists** | It does. This is the flowchart's *No* branch — a record is never discarded |
| 7.8 | Correct a reading while it is back | Allowed — and the CFT is asked to look again, so nobody approves a version they never saw |
| 7.9 | Have both CFT members approve, then **Approve** the final decision | Fully approved |

---

### B8 · Filing it — `s.iyer`

| Step | Do this | ✅ Expect |
|---|---|---|
| 8.1 | Open **Storage** | The approved record is in *Waiting to be filed* |
| 8.2 | Press **File it on the server** | Filed at `Records / Process Quality / QF-PQ-001 / 2026 / 09-Sep / 02` |
| 8.3 | Compare a **monthly** format's path | It stops at the month; a **weekly** one is filed under its ISO week |
| 8.4 | As `a.deshmukh`, try to file something | **Refused** — filing is the Overall Process Owner's act |

> Nobody maintains that folder tree. It is built from the format's frequency.

---

### D2 and B9 · Change control — `r.kumar`, then `m.shaikh`

| Step | Do this | ✅ Expect |
|---|---|---|
| 9.1 | As **`admin`**, try to edit an active format | **Refused** — every change goes through a change request |
| 9.2 | As **`r.kumar`** → **Change Request**, raise one against QF-PQ-001 | |
| 9.3 | Try to raise a second one on the same format | **Refused** — one open request per format |
| 9.4 | Try to approve your own | **Refused** |
| 9.5 | Sign in as **`m.shaikh`** | It is waiting on you, and on nobody else |
| 9.6 | Try to **execute** before approving | **Refused** — "approved before execution" |
| 9.7 | **Approve** it | Note **nothing has changed yet** — approving *authorises* the change |
| 9.8 | Press **Create the next revision** | Revision 01 created |
| 9.9 | Open **Formats** | Rev 00 **superseded**, rev 01 a **draft**. Release it |
| 9.10 | Open a record filed earlier | It still says **rev 00**. History cannot be rewritten by a later change |

---

### The whole picture

| Step | Do this | ✅ Expect |
|---|---|---|
| 10.1 | As `admin` → **Record Register** | Four counts at the top |
| 10.2 | Press **Needs re-verification** | Filters to the red ones |
| 10.3 | In a terminal: `python cli.py records` | The same picture without a browser |

---

# Part 3 · Demonstrating it in ten minutes

> A fuller, screen-by-screen version of this — which menu item to open in what
> order, what to say at each one, the seven-minute cut, and the questions a
> manager asks — is in **[DEMO.md](DEMO.md)**.


Sign in as `admin` first, seed loaded, one screen. **Do the OCR scan once
before they arrive** so the models are warm and it takes 5 seconds, not 30.

| # | Show them | Say |
|---|---|---|
| 1 | **Formats** | "Every blank format lives on the server with the frequency it is filled at, the limits each reading must meet, and the four people who act on it. Nobody builds an approval chain by hand." |
| 2 | **Record Register** → press the red tile | "Three colours, exactly as the process defines them. Red means a record needs to go back to the CFT. One click and here they are." |
| 3 | Sign in as `r.kumar` → **Fill Record** | "The menu *is* the process. This person is offered only the formats they own, for the period that is due." |
| 4 | Type an out-of-spec reading | "ok or N-ok is decided by arithmetic against the limit on the row, before anybody is asked to approve it." |
| 5 | **Attach the scanned hard copy** | "They keep filling the paper form exactly as they do today. It is photographed, and the readings come back off it — including the table, still a table." |
| 6 | Point at the suggestions | "96% confident, and it tells you what each value *would mean* before you accept it. Nothing is recorded until a person confirms it." |
| 7 | Sign in as `s.iyer` → **Tracking** | "An out-of-spec reading flags the Overall Process Owner the moment it is submitted — it does not wait in the queue — and the record cannot be filed until the action taken is recorded." |
| 8 | As `a.deshmukh`, approve → back to **Tracking** | "The joint review is *joint*. One member agreeing does not conclude it." |
| 9 | As `r.kumar`, **Send back to the CFT** | "This is the part a generic approval tool gets wrong. Rejecting the final decision does not throw the record away — it goes back to the CFT, turns red, and every earlier CFT approval is cleared. Nothing is ever lost." |
| 10 | **Storage** | "Filed into date and month folders built from the format's frequency. No one maintains this tree." |
| 11 | As `m.shaikh` → **Change Request** | "And no format changes without the QMS Coordinator approving it first. The old revision is superseded, never deleted, and records keep the revision they were filled against." |

**Finish with this on screen.** It is the most convincing thing in the
repository:

```bash
.venv\Scripts\python scripts\validate_workflow.py
```

It signs in as all seven people, walks the entire flowchart against the running
system, and prints one line per business rule — 106 of them.

---

## If something looks wrong

| Symptom | Cause | Fix |
|---|---|---|
| First scan takes ~30 s | OCR models loading, once per server run | Normal. Scan once before a demo |
| Scan says the sheet is corrupt | The identical file is already another record's evidence | Deliberate — two records cannot share one sheet |
| `cli.py ocr` says PaddleOCR not installed | Optional dependency | `pip install -r requirements-ocr.txt` |
| Readings not suggested after a scan | The sheet is not laid out as a grid, or the labels differ from the format's | Type them; a wrong table is worse than none |
| Server will not start on Windows | `python-magic` has no DLLs | `pip install python-magic-bin==0.4.14` |
| Semantic search stopped working | PaddleOCR 2.x downgraded protobuf | Use the pins in `requirements-ocr.txt` |
| A format will not release | It is missing a responsibility, a reading, or somebody has left | The screen lists exactly what is missing |
