# How to demonstrate this system

**Read this if you have never seen this project before.**

You do not need to be a programmer. You do not need to understand any code. You
need **about 20 minutes with your manager** and this page open beside you.

You will sign in **once**, as `admin`, and stay signed in for the whole demo.

---

# Part 1 · What you are actually showing

## The problem, in one paragraph

HARMAN's quality teams fill in inspection forms **on paper**. Somebody measures a
part, writes the reading on a printed sheet, signs it, and the sheet goes into a
file. If a customer later asks *"show me the check you did on 2 September"*,
somebody has to walk to a cabinet and find the paper. If a reading was outside
its limits, nobody outside that room knows unless the paper is read. And if the
form itself needs changing, a new version gets photocopied while old copies stay
in circulation.

## What this system does

It moves all of that onto a computer **while keeping the exact process HARMAN
already uses**. Nothing was invented or simplified. HARMAN gave us a flowchart,
and the system follows it box by box.

Three things are worth saying out loud early:

1. **The paper still works.** People can fill the form on screen, or keep filling
   it on paper and photograph it. The system reads the photograph.
2. **The process is enforced, not merely recorded.** You cannot file a record
   that skipped an approval. The system refuses.
3. **Nothing is decided by the computer.** It reads, it suggests, it checks
   limits, it routes work to the right person. A human signs every decision.

## The flowchart, in plain English

HARMAN's document labels each step **B1 to B9**, with two decision points **D1**
and **D2**. You will hear those labels throughout this guide, so here they are in
ordinary words. **Keep this table handy during the demo** — every act below tells
you which box it is showing.

| Box | The official wording | What it actually means |
|-----|----------------------|------------------------|
| **B1** | Blank formats stored on server, filled at various frequency | Keep the *blank* forms in one place, so everyone uses the current version |
| **B2** | Process Owner calls the format to be filled | The person doing the check picks the form they need |
| **B3** | Record filled as per work instruction | They fill it in — on screen, or on paper and photographed |
| **B4** | Record approved by Process Owner if within specification | Two approvals: the Process Owner, then the Overall Process Owner |
| **B5** | Record stored with status ok / N-ok | Anything outside limits raises a **flag** to the Overall Process Owner |
| **B6** | Joint review triggered to CFT members with target date | A cross-functional team reviews it and gives an opinion |
| **B7** | Final decision on record approval | The Process Owner decides, having heard the CFT |
| **D1** | Record approved / rejected? | **Yes** → file it. **No** → back to the CFT to be re-verified |
| **B8** | Records stored on server for further storage | The record is filed permanently, in dated folders |
| **D2** | Any change to the format needed? | **No** → finished. **Yes** → B9 |
| **B9** | Change request raised and approved before execution | The form itself can only be changed by a formal request |

## The one thing to understand about approvals

Four different people are named on every form:

| Role | What they do |
|------|--------------|
| **Process Owner** | Fills the record, approves it, takes the final decision |
| **Overall Process Owner** | Second approval, handles out-of-limit flags, files the record |
| **CFT members** | The cross-functional team who give an opinion |
| **QMS Coordinator** | The only person who can approve a change to the form itself |

**In real use these are four different people, and the system will not let one
person sign in another's place.** If a step belongs to Ravi Kumar, even the
system administrator is refused — the screen says *"This step is assigned to Ravi
Kumar."*

**For this demo you will make yourself all four**, purely so you are not signing
in and out six times in front of your manager. **Say that out loud when you get
there.** It is worth saying, because it lets you point out that the system
normally prevents exactly this.

---

# Part 2 · Setting up (before your manager arrives)

Open a terminal in the project folder. **Two commands, every time:**

```bash
python scripts/reset_demo.py --yes    # 1. a clean, known starting state
python cli.py serve                   # 2. start it - leave this window open
```

The first one builds the database, adds the teams, the people and four worked
examples, and stamps a fresh pair of inspection sheets. It is also how you
**reset between rehearsals** — run exactly the same command again.

> ⚠️ **Stop the server before resetting.** It holds the database open, and the
> script will tell you so rather than half-resetting. Press `Ctrl+C` in the
> window running `serve`, reset, then start it again.

> **If Windows says `python` was not found**, use the project's own copy:
> `.venv\Scripts\python.exe scripts\reset_demo.py --yes`, and the same for
> `serve`.

When the second command says it is running, open a browser at:

### **http://127.0.0.1:8000**

### The two accounts you will use

| Who | Sign in as | Their part |
|-----|-----------|------------|
| **You** | `admin` | Build the form, fill the record, watch it move |
| **Aryan Sharma** | *(never signs in)* | Process Owner. Answers from a link in his inbox |

Everybody the seed creates uses the same demo password. It is not published
here: ask the project administrator for it. Aryan is the point of the
demonstration: he is a second, real person who approves a record **without ever
signing in**, and his decision appears on your screen while your manager
watches.

## The two sample sheets

Command 3 above created two files in the project folder:

| File | What is on it |
|------|---------------|
| `harman-inspection-sheet.pdf` | A filled inspection form, **every reading inside limits** |
| `harman-inspection-sheet-nok.pdf` | The same form, but bore diameter is **26.45 mm — outside limits** |

They look like a page that came off a scanner: slightly crooked, slightly grey,
slightly soft. Importantly, they contain **no hidden text — they are pictures**.
That matters, because it means when the system reads them it is genuinely
reading, not copying text that was already inside the file.

**You will use the N-OK one**, because a sheet that fails shows far more of the
process than a sheet that passes.

> ### ⚠️ A sheet can only ever be used once
> The system refuses to accept the same hard copy as evidence for two different
> records. That is deliberate — it stops anyone quietly reusing a sheet. So
> **before demonstrating a second time**, run:
>
> ```bash
> python scripts/make_sample_sheet.py --fresh
> ```
>
> That keeps every reading identical (so this guide still matches) and just
> stamps a new batch number, which makes them count as new sheets.

## Two minutes of warm-up — strongly recommended

The **first** time the system reads a scan after starting, it loads its reading
software, which takes about **30 seconds**. Every scan after that takes about
**5 seconds**.

Do that first read *before* your manager sits down, so they see 5 seconds rather
than 30.

**Warm it up with any other PDF — not one of the demo sheets.** Attaching a demo
sheet spends it, and it cannot then be attached again during the real demo. So:
follow **Act 2** below as far as **Attach the scanned hard copy**, upload any
random PDF you have lying around, then close the record without submitting. The
reading it produces will be nonsense, which does not matter — the models are now
loaded.

*(If you do accidentally spend a sheet, `python scripts/make_sample_sheet.py
--fresh` gives you a new pair in a second.)*

## What you should see

Across the top of every screen is a numbered rail. **That rail is the
flowchart**, and it is your entire demo:

| Step on the rail | The boxes it covers |
|------------------|---------------------|
| **1 · Form Templates** | B1 — the blank forms, and how each one is approved |
| **2 · My Forms** | B2, B3 — call a form and fill it, or scan the paper |
| **3 · My Approvals** | B4, B6, B7 — every signature |
| **4 · Status Tracking** | B5, D1 — flags, status, sending back |
| **5 · Filed Records** | B8 — filing it permanently |
| **6 · Change Requests** | B9 — changing the form itself |

Behind **More** sit four screens that are not steps of the process: **All
Records**, **Notifications** (every message the system has sent), **People &
Teams**, and the **Activity Log**.

The box numbers are not printed on screen. They are in this guide and in the
technical documentation, for anybody checking the product against HARMAN's
document — a line supervisor does not need to know what B5 is called.

**Open your demo by pointing at the rail.** Say:

> *"That row across the top is HARMAN's flowchart, in order, on every screen.
> We are going to walk it one step at a time."*

It is the single most useful sentence in the whole demo.

---

# Part 3 · The story you are telling

Give the demo a situation. It is far easier to follow than a tour of screens.

> **The scene.** It is the end of the morning shift at the Chakan plant. Ravi
> Kumar has been checking bores on the CNC-3 line. He filled in the inspection
> sheet on paper, as he always does. One part came out oversize.
>
> We are going to follow that one sheet — from the paper in his hand, to a
> signed and permanently filed quality record — and then change the form itself.

---

# The demo

**Seven acts, about 20 minutes.** Each act tells you **what to do**, **what to
say**, **why it matters**, and **which box of the flowchart it is**.

---

## Act 1 · The blank form ▸ Box **B1**

### 📍 On the rail: `1 · Form Templates`

### What to do

1. Click **Form Templates**. The three quality teams' forms are already there.
2. Click into **QF-PQ-001** and show what is inside: the readings it asks for,
   the limits on each one, the four people responsible, how often it is filled,
   and where its records will be stored.
3. Now click **New format** (top right) and fill in:

| Field | Put this |
|-------|----------|
| Code | `QF-DEMO-01` |
| Title | `In-Process Dimensional Check (demo)` |
| Choose a team | Process Quality |
| Filled how often | Daily |
| Work instruction | `WI-PQ-014` |

4. Click **Add a reading** five times and enter:

| Reading | Type | Limits |
|---------|------|--------|
| Bore diameter | Number | min `24.90`, max `25.10` |
| Surface finish | Number | max `1.6` |
| Run-out | Number | max `0.05` |
| Gauge serial | Text | — |
| Operator | Text | — |

5. **Set all four responsibilities to yourself** (System Administrator): Process
   Owner, Overall Process Owner, QMS Coordinator, and add yourself as the CFT
   member.
6. Save, then click **Release**.

### What to say

> "This is the blank form. Not a Word file on somebody's desktop — one master
> copy, on the server, with the limits built into it. Every reading knows what
> 'good' looks like before anybody fills it in."

> "And it will not let me release this until all four responsible people are
> named, and are people who can actually sign. An unstaffed form cannot go live."

**Then be straight with them:**

> "I am putting my own name in all four roles just for this demo, so I don't have
> to log in and out six times. In real use these are four different people — and
> the system refuses to let one person sign in another's place. I'll show you
> that refusal later."

### Why this matters

This is **B1** — the client's own words are *"all blank formats need to be stored
on server."* The point is version control: when a form changes, everybody gets
the new one at once, because there is only ever one.

---

## Act 2 · Designing the sheet ▸ still Box **B1**

### 📍 On the rail: `1 · Form Templates` → **Design the form**

This is the act that answers *"can we make it look like our form?"*, which is
the first question anybody in quality asks.

### What to do

1. On your draft `QF-DEMO-01`, press **Design the form**.
2. The designer opens on a standard inspection sheet. The right-hand side shows
   **the sheet as it will be printed** — it updates as you change anything.
3. Show the pieces: the **header** with the HARMAN letterhead and the job
   details, a **checklist** of things to confirm before starting, the **table**
   of readings, **entries** for observations, and the **signature** spaces.
4. Change something visible — add a row to the table, or add a checklist item —
   and let them watch the sheet on the right change with it.
5. Press **Save the form**.

### What to say

> "This is your form, not ours. The letterhead, the job details, the ruled
> table, the tick boxes, the signature spaces at the bottom — it is the sheet
> you already use, rebuilt here."

**Point at the counter above the editor** (*"11 things recorded"*):

> "And this is the part that matters. Everything the form records is worked out
> from the design. There is no second list to keep in step with it, so the sheet
> and the data can never disagree."

**Point at a column marked "Printed only":**

> "A specification column is printed on the sheet but never filled in. The
> system knows the difference, which is how it can tell you a reading is out of
> limits without anybody teaching it what the limits are."

### Why this matters

Still **B1** — *"all blank formats need to be stored on server"*. The client's
document says the blank forms live centrally; this is what "the blank form"
actually is once it is on a computer.

---

## Act 3 · Reading the paper sheet ▸ Boxes **B2** and **B3**

### 📍 On the rail: `2 · My Forms`

**This is the act that wins the room. Slow down here.**

### What to do

1. Click **My Forms**.
2. Find **QF-DEMO-01** and press **Fill it here**. A record is created for today.
   - Point at the record number and today's date, and say: *"That's B2 — the
     Process Owner has called the form for this period."*
3. *(Optional, 15 seconds, and effective)* Type a bore diameter of `25.0` — it
   shows as ok. Change it to `26.5` — it immediately shows N-ok. Then clear it.
4. Click **Attach the scanned hard copy**.
5. Upload **`harman-inspection-sheet-nok.pdf`** from the project folder.
6. Wait about 5 seconds (30 if you skipped the warm-up).

### What you will see

- **All five readings, filled in automatically** and matched to the right boxes:
  bore diameter 26.45, surface finish 0.92, run-out 0.038, gauge serial BG-4471,
  operator R. Kumar.
- **Bore diameter marked N-ok**, because 26.45 is above the 25.10 limit.
- **"The table it recovered"** — expand this. The table from the paper sheet has
  been rebuilt as a table, rows and columns intact.

### What to say

> "Ravi filled this in on paper at the end of his shift and photographed it. That
> is all he did."

> "The system has read that slightly crooked, slightly grey scan and put every
> reading in the right box. And notice it hasn't just pulled out text — it has
> kept the **structure**. The table is still a table. Row three is still run-out.
> That is what stops a reading landing against the wrong characteristic."

**Point at the N-ok bore diameter:**

> "And it checked it against the limit while he was still standing at the
> machine. He knows now, not next week."

**Then the important sentence:**

> "But look — nothing has been saved yet. These are *suggestions*. The system
> will not write a quality reading into a record on its own. Ravi has to look at
> each one and confirm it."

7. Press **Use all of these**, then **Submit for approval**.

### The other half of B3 — thirty seconds, worth doing

The paper sheet is one route. The same box also covers the operator who fills
the form at a terminal and never prints anything.

1. Go back to **My Forms** and pick any form with **Fill it here**.
2. Type **one** reading and leave the rest blank.
3. The button now reads **Submit anyway**, and the panel says plainly what is
   missing. Press it.

> "Nothing was scanned, and the form is half done — and it still went forward.
> The blanks are recorded against the record and shown to the approver before
> they sign. We are not going to send a supervisor away with readings in his
> hand and nowhere to put them. That is how measurements end up on a scrap of
> paper."

> "And the record still has a document behind it: the system saved the filled
> form as a PDF. An auditor opening this in five years gets a page, whether or
> not anybody ever held one."

### Why this matters

This is **B3**, and it is why HARMAN asked for this system at all. Their words
were *"hard copy digitalization using OCR."* The value is not typing less. The
value is that an out-of-limit reading is caught **at the machine**, and the sheet
becomes searchable the moment it is photographed.

---

## Act 4 · The out-of-limits flag ▸ Box **B5**

### 📍 On the rail: `4 · Status Tracking`

### What to do

1. Go to **Status Tracking** and open your record.
2. A red banner is showing: **"N-ok observations, flagged for further action."**

### What to say

> "The moment Ravi submitted, the system saw a reading outside its limit and
> **raised a flag to the Overall Process Owner**. Nobody had to remember to do
> that. Nobody had to send an email."

> "And here is what matters for an audit: **this record cannot be filed while
> that flag is open.** The system will not let it through. Somebody has to write
> down what was actually done about it."

3. Click **Record the action taken** and type something real:

   > `Batch B-2609 quarantined. Tool offset corrected on CNC-3, first-off re-checked and found within limit.`

4. Save. The banner turns green.

### Why this matters

This is **B5** — *"any N-ok observation raises a flag to the Overall Process
Owner for further action."* The system turns that sentence into something that
physically blocks progress until it is answered. That is the difference between
a procedure and a control.

---

## Act 5 · The four signatures ▸ Boxes **B4**, **B6**, **B7**

### 📍 On the rail: `3 · My Approvals`

This is where you show the process being enforced.

### What to do

Click **My Approvals**. The remaining tasks are waiting, and they arrive **one at a time, in
order**. Work through them in sequence:

| # | The task | Who it belongs to in real life | Box |
|---|----------|-------------------------------|-----|
| 1 | **Process Owner approval** | The person who did the check | **B4** |
| 2 | **Overall Process Owner approval** | Their manager | **B4 condition** |
| 3 | **CFT joint review** | The cross-functional team | **B6** |
| 4 | **Final decision** | The Process Owner, having heard the CFT | **B7** |

For each: click **Approve & sign**, draw a signature, confirm. Then **Refresh** —
the next one appears.

**Pause on tasks 3 and 4 before approving.**

### What to say

**Before you start:**

> "Four signatures, and they appear one at a time. I cannot sign number three
> before number two exists. There is no way to skip a step, because the next step
> is not there to be skipped."

**At the CFT joint review (task 3)** — point at the buttons:

> "This is the cross-functional review — B6. Manufacturing and Quality look at
> the record together, against a target date."

> "And look at what the negative button says. It does not say *Reject*. It says
> **Object**. That is deliberate, and it comes straight out of HARMAN's document:
> the CFT's job is to *inform* the final decision, not to take it. An objection
> is recorded and carried forward to the person who does decide."

**At the final decision (task 4)** — point at the buttons again:

> "This is B7 — the final decision, taken by the Process Owner **after** hearing
> the CFT. And notice this button says **Send back to the CFT**, not *Reject*.
> That is decision point D1: if the answer is no, the record does not die — it
> goes back up to the CFT to be re-verified, and it turns red in tracking until
> it is. A generic approval tool would have ended the process and the record
> would be gone."

**If your manager looks sceptical about enforcement**, say:

> "If I had left the Process Owner as Ravi Kumar and tried to sign it myself as
> administrator, the system would have said *'this step is assigned to Ravi
> Kumar'* and refused. Administrator rights do not let you sign as somebody
> else."

*(You can prove it: open **All Records**, pick one of the seeded records belonging
to Ravi Kumar, and try to approve it. It refuses.)*

### Why this matters

This is the heart of the flowchart. **B4, B6 and B7 are three separate approvals
with three different meanings**, and the wording on every button matches HARMAN's
own document rather than generic approve/reject software.

---

## Act 6 · Aryan approves from his inbox ▸ Boxes **B4**, **B6**

**This is the act the demonstration exists for.** Take it slowly.

### 📍 On the rail: **More → Notifications**

Everything so far has been one person at one screen. Now a second person, who
has never been shown this system, answers an approval from a link — and your
screen changes while your manager watches.

### Before you start

Open a **second browser window, private/incognito**, and leave it on the sign-in
page. Two normal windows share one session and will sign each other out.

### What to do

1. In your main window, open **Notifications**.
2. Find the newest message — the one asking for approval on the record you just
   submitted. Show the room what it contains: who it went to, the record, the
   readings, and the link at the bottom.
3. **Copy the approval link** and paste it into the private window.
4. In the private window, the approval page opens — **with nobody signed in.**
5. Show what it says: the record, every reading against its limits, the
   out-of-limits one in red, and a link to the scanned sheet.
6. Write a comment, draw a signature, and press **Approve and sign**.
7. Switch back to your main window, open **Status Tracking**, and refresh.

### What to say

**Opening Notifications:**

> "Every notification the process asks for is written down before we even try to
> send it. So this is the record that the trigger fired — whether or not the mail
> server was up. On this laptop there is no mail server at all, which is why they
> all say *Not emailed*, and the link still works."

**Pasting the link into the private window:**

> "This is Aryan. He is a Process Owner on the assembly line. He has not signed
> in — he does not need to. The link is his, it works once, and it expires."

**On the approval page:**

> "He sees the record, every reading against its limit, and the one that failed
> in red. He can open the photograph of the paper sheet. He is not being asked
> to trust a summary."

**Point at the buttons:**

> "And notice there is no *Reject*. A quality record is never thrown away, so the
> negative answer says what actually happens to it — here, *Return for
> correction*, which unlocks the readings to be put right."

**After he signs, back on your screen:**

> "That decision is now on my screen, against his name, with his signature and
> the time he gave it. He never signed in, and I could not have signed it for
> him — the system refuses that even to an administrator."

### Prove the link is spent

Press the link a second time in the private window.

> "Used once. If he forwards that email to somebody, they get this, not a second
> vote."

### Why this matters

**B4** and **B6** both say *"implement a trigger email notification ... for
approval"*. An email that only says "sign in and go and find it" is barely
better than no email — the person is on a shop floor, on a phone, and the
distance between reading the message and answering it is where approvals die.

---

## Act 7 · Filing it ▸ Box **B8**

### 📍 On the rail: `5 · Filed Records`

### What to do

1. Click **Filed Records**. Your record is under **Waiting to be filed**.
2. Read out the **"Will be filed at"** path shown beside it.
3. Click **File it on the server**.

### What you will see

The record is filed at a path built automatically:

```
Records / Process Quality / QF-DEMO-01 / 2026 / 09-Sep / 02
```

### What to say

> "Nobody chose that folder. The system built it — team, then form, then year,
> then month, then day — because this form is filled **daily**. A weekly form
> would stop at the week. A monthly one at the month."

> "That is straight out of the document: *'date-wise / month-wise folders created
> based on record generation frequency.'* The filing structure follows the form's
> frequency, so it is the same for everybody, forever."

> "And remember — five minutes ago it would not have let me get here, because
> that N-ok flag was still open."

### Why this matters

**B8.** It is the difference between "we save our records somewhere" and "our
records are filed in a predictable place, by rule, where an auditor can find them
without asking anybody."

---

### And the record itself

From **All Records** or **Filed Records**, press **View the record** on the one
you just filed.

> "This is what the process produces. The form as we designed it, the readings
> that were taken, which of them failed, and the signatures of the four people
> who approved it — with their designations and the times they signed."

Press **Print this record**.

> "That is what goes in the file, and what an auditor asks for. Nobody retypes
> anything to produce it."

---

## Act 8 · Changing the form itself ▸ **D2** and **B9**

### 📍 On the rail: `6 · Change Requests`

### What to do

1. Click **Change Request**, then **Raise a change request**.
2. Fill it in:

| Field | Put this |
|-------|----------|
| Format | QF-DEMO-01 |
| Type | Change to an existing format |
| Title | `Add coolant temperature check` |
| Justification | `Customer complaint traced to coolant drift. Add a coolant temperature reading, 18-24 C.` |

3. Click **Send to the QMS Coordinator**.
4. Open the request and click **Approve**.
5. **Stop here for a moment**, then click **Create the next revision**.

### What to say

> "Six months in, Quality decides this form needs an extra reading. In the paper
> world somebody edits the master, photocopies it, and for the next three months
> half the plant is still using the old sheet."

> "Here the form **cannot be edited directly at all**. The only way in is a change
> request, and it goes to the QMS Coordinator — the one role HARMAN's document
> names for it."

**After approving, before executing** — this is the point worth pausing on:

> "Notice approving is not the same as doing. It has been approved, but the live
> form has not changed. Somebody still has to execute it. HARMAN's wording is
> *'approved before execution'* — two separate acts, so a rubber-stamped approval
> cannot accidentally go live."

**After executing** — go to **Form Templates** and show the result:

> "Revision 00 is now superseded and revision 01 is a draft. The old revision is
> never deleted, because every record already filed was filled against revision
> 00 and has to stay readable against the form it was actually filled on. A
> change made today cannot rewrite what was measured last month."

### Why this matters

**D2 and B9.** This is the answer to *"how do you stop old versions
circulating"* — the question every quality manager asks, and the reason document
control exists at all.

---

## Act 9 · The whole plant on one screen — 2 minutes

### 📍 On the rail: `All Records` (under **More**)

You have now walked the entire flowchart. Finish by showing that the system
already holds the awkward cases too — this is not a one-happy-path demo.

Point at the coloured status on each record:

| What you see | What it means | Box |
|--------------|---------------|-----|
| 🟢 **Ok for final review** | Everything in limits, ready to decide | B6 condition |
| 🟡 **Filling in progress** | Somebody is still working on it | B6 condition |
| 🔴 **Needs re-verification** | Sent back by D1, or carrying an open flag | D1 |

Press the **red** filter.

### What to say

> "Every released record has a colour, and the three colours are the three
> HARMAN specified: green ready for final review, yellow being filled, red needs
> re-verification with the CFT. It also tells you *why* each red one is red."

> "So a quality head opens one screen in the morning and knows where every record
> in the plant stands — without asking anybody, and without walking to a filing
> cabinet."

---

# After the demo

## Questions your manager will probably ask

| Question | Answer |
|----------|--------|
| **"What about lines that don't use paper at all?"** | The form is filled on screen and submitted directly. The system saves the completed form as a PDF, so the record has a document behind it either way. Scanning is a route, not a requirement. |
| **"What if a reading can't be taken this shift?"** | The record goes forward with the blank recorded against it, and the approver is told before they sign. It is a warning, not a locked door — somebody still has to answer for it. |
| **"Does this need the internet?"** | No. It runs on your own server. The scan reading happens on that machine — no record ever leaves the building. |
| **"How accurate is the scanning?"** | On our sample sheets it read all five readings correctly, at about 97% confidence. And it never writes a value on its own — a person confirms every one. |
| **"What if it reads something wrong?"** | The person filling the record sees the suggestion beside the picture and corrects it before saving. Nothing is accepted automatically. |
| **"Can somebody skip an approval?"** | No. The next step does not exist until the previous one is answered, and a step assigned to one person cannot be signed by another — including by an administrator. |
| **"Can somebody approve their own work?"** | Not where the process forbids it. The Process Owner cannot close their own N-ok flag, and nobody approves their own change request. |
| **"Can we still use paper?"** | Yes — that is the design. Paper is filled exactly as now, photographed, and the record is built from the photograph. |
| **"What if somebody leaves the company?"** | The form reports it and refuses to be released until somebody else is appointed to that role. |
| **"What if the form needs changing?"** | Only through a change request approved by the QMS Coordinator — and approving it is a separate act from executing it. |
| **"Where do records actually go?"** | Into dated folders on your server, built automatically from the form's frequency. You saw the path. |
| **"Is there an audit trail?"** | Yes — every action, who did it, when, with their signature. That is the **Status Tracking** screen and the Activity Log. |
| **"How long to add our real formats?"** | About ten minutes each: code, team, frequency, the four people, then the designer for the sheet itself. |
| **"Can one person do it all, like you just did?"** | Only because I gave myself all four roles for this demo. On a real form those are four different people, and the system enforces it. |

## If something goes wrong during the demo

| What you see | What to say | What to do |
|--------------|-------------|------------|
| The first scan takes ~30 seconds | *"It's loading the reading software — that happens once after a restart."* | Warm it up beforehand (Part 2) |
| *"That exact file is already the evidence for REC-…"* | *"That's the system refusing to let one sheet be used for two records — which is the point."* | Run `python scripts/make_sample_sheet.py --fresh` in another window, then attach the new sheet |
| *"This step is assigned to …"* | *"That's it refusing to let me sign in somebody else's name."* | You are on a seeded record. Use your own `QF-DEMO-01` record |
| A record will not file | *"There's still an open out-of-limits flag."* | Tracking → **Record the action taken** |
| **Release** is greyed out on a format | *"It won't release a form with a responsibility unfilled."* | Fill in all four roles |
| No readings were suggested from a scan | *"The sheet isn't ruled as a grid, so it won't guess — a wrong table is worse than none."* | Type them in, or use our sample sheet |
| A button you expected is missing | — | Check the name at the bottom-left; you may be signed in as somebody else |
| Nothing loads at all | — | Check the `python cli.py serve` window is still running |

## Resetting for a second run

**One command puts everything back.** Stop the server first (Ctrl+C in the
window running `serve`), because it holds the database open:

```bash
python scripts/reset_demo.py       # asks before it deletes anything
python cli.py serve                # start it again
```

That is the whole reset. It wipes the database, clears the filed evidence, and
stamps a fresh pair of sample sheets — so the sheets in the project root are
attachable again, your `QF-DEMO-01` format is gone, and you are back to exactly
the state described in Part 2.

Add `--yes` to skip the confirmation. The script refuses to run while the server
is up, and tells you so, rather than half-resetting.

**If you only hit the "already the evidence for…" message** and everything else
is fine, you do not need a full reset — just stamp new sheets:

```bash
python scripts/make_sample_sheet.py --fresh
```

## Proving it works, without clicking

If your manager wants evidence rather than a tour, run this with the server
still running:

```bash
python scripts/validate_workflow.py
```

> ⚠️ **Run this *after* the demo, not before.** To test the process it has to
> create formats and records of its own, and it leaves about two dozen of them
> behind, all named `QV-…`. They are harmless, but they will clutter the Form Templates
> screen and the Record Register if your manager looks at those afterwards. Clear
> them with the clean slate steps above.

It signs in as each real person in turn and runs **106 checks** against HARMAN's
flowchart, printing which box of the document each one defends. It ends with:

```
106 checks passed. The system matches the process flow.
```

And the code's own test suite:

```bash
python -m pytest tests/ -q          # 312 tests
```

---

# One-page cheat sheet

*Print this bit and keep it beside you.*

**Sign in:** `admin` / *(the demo password from the project administrator)* at **http://127.0.0.1:8000**
**Second window:** private/incognito — Aryan answers from a link, not an account
**Sheet to use:** `harman-inspection-sheet-nok.pdf` — bore diameter 26.45, out of limits
**Before a repeat demo:** stop the server, then `python scripts/reset_demo.py --yes`

| # | Where | What you do | Box |
|---|-------|-------------|-----|
| 1 | **Form Templates** | Create `QF-DEMO-01`, name **Aryan** as Process Owner, yourself in the rest | B1 |
| 2 | **Design the form** | Show the sheet building live on the right. Add a row. **Save the form** | B1 |
| 3 | **My Forms** | **Fill it here** → **Attach the scanned hard copy** → the N-OK sheet → **Use all of these** → **Submit** | B2, B3 |
| 4 | **Status Tracking** | Red flag → **Record the action taken** | B5 |
| 5 | **More → Notifications** | Copy Aryan's approval link | B4 |
| 6 | **Private window** | Paste it. Read the record, comment, sign, **Approve** | B4, B6 |
| 7 | **Status Tracking** | Refresh — his decision is there, with his signature | — |
| 8 | **My Approvals** | **Approve & sign** the rest of the chain | B4, B6, B7 |
| 9 | **Filed Records** | **File it on the server**, read out the dated path | B8 |
| 10 | **View the record** | The finished sheet, signed. **Print this record** | — |
| 11 | **Change Requests** | Raise → **Approve** → **Create the next revision** | D2, B9 |

**If you have five minutes, do 1 → 3 → 5 → 6 → 7 → 10.** That is the whole
story: a form, filled, approved by somebody else from their inbox, and the
signed record that comes out.

**The one sentence to open with:**

> *"That row across the top is HARMAN's flowchart, in order, on every screen.
> We are going to walk it one step at a time."*
