"""
QMS - Record filling and record approval.

These tables implement the client's "Record filling & Record Approval Process
Flow" chart. Each one carries the box of that chart it exists to serve, because
a reader six months from now needs to know which rule in the process a column
is defending.

The chart's shape, in one paragraph: blank *formats* live on the server and are
filled at a stated frequency (B1). A Process Owner calls one (B2) and fills it
per the work instruction (B3). They approve it if it is within specification
(B4) and store it with an ok / N-ok status (B5). Any N-ok raises a flag to the
Overall Process Owner. A joint review goes to the CFT with a target date (B6),
the final decision is taken (B7), and an approved record is filed into date- or
month-wise folders (B8). A rejection at the final decision does NOT end the
process: it returns to the CFT for re-verification. Changing a format at all
requires a change request approved by the QMS Coordinator (B9).

They live in their own module rather than in `models.py` so the QMS domain can
be read as one piece. `models.py` imports this at the bottom, so importing
either module registers every table on the shared metadata.
"""
from uuid import uuid4

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Table, Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base

# --------------------------------------------------------------- vocabulary
#
# Named once, here, so a typo cannot invent a new frequency or a fourth colour.

FREQUENCIES = [
    "shift", "daily", "weekly", "monthly", "quarterly",
    "half_yearly", "yearly", "per_event",
]

FORMAT_STATUSES = ["draft", "active", "superseded", "withdrawn"]

# What a reading that failed leads to. Corrective answers "this batch is out of
# specification, what are we doing about it"; preventive answers "what stops it
# happening again". ISO 9001 names both and the client's forms print both, so
# the two are one table with a kind rather than two tables that drift apart.
ACTION_CORRECTIVE = "corrective"
ACTION_PREVENTIVE = "preventive"
ACTION_KINDS = [ACTION_CORRECTIVE, ACTION_PREVENTIVE]

ACTION_OPEN = "open"
ACTION_CLOSED = "closed"
ACTION_STATUSES = [ACTION_OPEN, ACTION_CLOSED]

# Different stages of the document

STAGE_FILLING = "filling" # Record is being filled in or drafted, not yet submitted for approval
STAGE_PO = "po_approval" # Awaiting approval from the Process Owner
STAGE_OPO = "opo_approval" # Awaiting approval from the Operations Process Owner
STAGE_CFT = "cft_review" # Review by the CFT
STAGE_FINAL = "final_decision" # The final accept/reject decision
STAGE_STORED = "stored" # Approved and archived in the repository
STAGE_CANCELLED = "cancelled" # The record was withdrawn or abandoned

STAGES = [
    STAGE_FILLING, STAGE_PO, STAGE_OPO, STAGE_CFT,
    STAGE_FINAL, STAGE_STORED, STAGE_CANCELLED,
]

# B5
OK, NOT_OK = "ok", "not_ok"

# B6 condition - the three colours the chart names, and nothing else.
GREEN, YELLOW, RED = "green", "yellow", "red"


# The CFT for a format: the people a joint review is addressed to (B6).
format_cft_members = Table(
    "format_cft_members",
    Base.metadata,
    Column("format_id", String, ForeignKey("formats.id"), primary_key=True),
    Column("user_id", String, ForeignKey("users.id"), primary_key=True),
)


class QualityTeam(Base):
    """
    One of the dedicated quality teams (process quality, and its siblings).

    A team owns formats and the people who act on them. It exists so that
    "who is the Process Owner?" has a different answer per team without three
    parallel installations of the product.
    """
    __tablename__ = "quality_teams"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    code = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    formats = relationship("Format", back_populates="team")


class FormatFolder(Base):
    """A reusable folder in which template formats can be filed."""
    __tablename__ = "format_folders"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    name = Column(String(100), nullable=False)
    path = Column(String(500), nullable=False, unique=True, index=True)
    parent_path = Column(String(500), nullable=True, index=True)
    created_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Format(Base):
    """
    A blank format held on the server, to be filled at a stated frequency (B1).

    The four responsibilities from the chart's left-hand column are fields on
    the format, not on the record. That is deliberate: the chart describes a
    *standing* process, so the same four people act on every record of a given
    format, and a record should never have to be told who approves it.

    Formats are revision controlled. Nothing here is edited in place once
    active - a change goes through a ChangeRequest (B9), which supersedes this
    row with a new revision. A record filled against revision 02 must keep
    saying revision 02 after revision 03 exists.
    """
    __tablename__ = "formats"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    code = Column(String, nullable=False, index=True)          # QF-PQ-001
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    team_id = Column(String, ForeignKey("quality_teams.id"), nullable=True, index=True)

    # How often a record of this format is generated. This single value drives
    # the date/month folder structure at B8, so it is not decoration.
    frequency = Column(String, nullable=False, default="daily")

    # Revision control (B9). `revision_of` points at the revision this one
    # replaced, so the chain back to the original is always walkable.
    revision = Column(String, nullable=False, default="00")
    revision_of = Column(String, ForeignKey("formats.id"), nullable=True)
    effective_date = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=False, default="draft", index=True)

    # B3: "Record to be filled as per Inspection/Process work Instruction."
    # The instruction is carried on the format so the person filling it never
    # has to go and find it.
    work_instruction_ref = Column(String, nullable=True)
    work_instruction = Column(Text, nullable=True)

    # B5: "Record to be stored as per given path". The root of the path; the
    # date/month levels below it are derived from `frequency` at B8.
    storage_path = Column(String, nullable=True)

    # B6: how long the CFT gets for a joint review, in days from the moment the
    # review is triggered. Becomes the step's target date.
    cft_target_days = Column(Integer, nullable=False, default=3)

    # The approval route, as JSON: an ordered list of steps, each naming who it
    # is addressed to, whether one of them decides or all of them must, whether
    # a signature is required, and how long they have.
    #
    # NULL means the four steps of the process document - Process Owner,
    # Overall Process Owner, the CFT joint review, then the final decision. It
    # is deliberately the default rather than a starting point somebody has to
    # opt into: the process is the specification, and a template that says
    # nothing about its route should follow it.
    approval_route = Column(Text, nullable=True)

    # The form's shape, as JSON: the header, its tables and their columns, the
    # checklists, the signature spaces - the sheet as it is printed.
    #
    # Presentation and structure only. Everything the form *records* is still a
    # FormatField, flattened out of this on save, so judging a reading against
    # its limits and matching what OCR read off a scanned sheet keep working
    # off one source of truth. NULL means "draw the fields as a plain list",
    # which is what every template made before the designer existed wants.
    layout = Column(Text, nullable=True)

    # The chart's four responsibilities.
    process_owner_id = Column(String, ForeignKey("users.id"), nullable=True)
    overall_process_owner_id = Column(String, ForeignKey("users.id"), nullable=True)
    qms_coordinator_id = Column(String, ForeignKey("users.id"), nullable=True)

    # The blank itself, as held on the server (B1). Optional: a format defined
    # purely by its fields needs no file, while a scanned paper format is one.
    blank_file_path = Column(String, nullable=True)
    blank_mime_type = Column(String, nullable=True)
    blank_file_size = Column(Integer, nullable=True)

    created_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    team = relationship("QualityTeam", back_populates="formats")
    process_owner = relationship("User", foreign_keys=[process_owner_id])
    overall_process_owner = relationship("User", foreign_keys=[overall_process_owner_id])
    qms_coordinator = relationship("User", foreign_keys=[qms_coordinator_id])
    creator = relationship("User", foreign_keys=[created_by])
    cft_members = relationship("User", secondary=format_cft_members)
    fields = relationship(
        "FormatField",
        back_populates="format",
        cascade="all, delete-orphan",
        order_by="FormatField.order_index",
    )
    records = relationship("Record", back_populates="format")
    reviews = relationship(
        "FormatReview",
        back_populates="format",
        cascade="all, delete-orphan",
        order_by="FormatReview.created_at",
    )


class FormatField(Base):
    """
    One line on a blank format, and the specification it must fall within.

    The specification limits are what make B4 ("if found within specification
    condition") and B5 ("status ok/N-ok") mechanical rather than a matter of
    opinion. A numeric value outside spec_min..spec_max is N-ok, and the system
    says so before anybody is asked to approve it.
    """
    __tablename__ = "format_fields"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    format_id = Column(String, ForeignKey("formats.id"), nullable=False, index=True)
    order_index = Column(Integer, nullable=False, default=0)

    label = Column(String, nullable=False)
    field_type = Column(String, nullable=False, default="text")
    # text | number | select | date | boolean

    unit = Column(String, nullable=True)
    spec_min = Column(Float, nullable=True)
    spec_max = Column(Float, nullable=True)
    # For non-numeric checks: the value that counts as conforming, e.g. "OK",
    # "Present". Compared case-insensitively.
    spec_text = Column(String, nullable=True)
    options = Column(Text, nullable=True)        # JSON list, for select
    required = Column(Boolean, nullable=False, default=True)
    help_text = Column(String, nullable=True)
    # Where the field sits on the designed layout (see form_layout.to_fields).
    layout_key = Column(String, nullable=True)

    format = relationship("Format", back_populates="fields")


class FormatReview(Base):
    """One approval run that releases a newly designed format when complete."""
    __tablename__ = "format_reviews"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    format_id = Column(String, ForeignKey("formats.id"), nullable=False, index=True)
    status = Column(String, nullable=False, default="pending", index=True)
    steps_json = Column(Text, nullable=False)
    current_step = Column(Integer, nullable=False, default=0)
    submitted_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    format = relationship("Format", back_populates="reviews")
    submitter = relationship("User", foreign_keys=[submitted_by])


class Record(Base):
    """
    One filled instance of a format, for one period (B2 through B8).

    The approval chain itself is an ApprovalWorkflow, built automatically from
    the format when the record is submitted. This row holds everything the
    generic engine has no concept of: which period it covers, whether the
    observations were ok or N-ok, its traffic-light status, and where it was
    finally filed.
    """
    __tablename__ = "records"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    number = Column(String, unique=True, nullable=False, index=True)

    format_id = Column(String, ForeignKey("formats.id"), nullable=False, index=True)
    # Frozen at creation. Revision 03 of a format must not rewrite the history
    # of a record filled against revision 02.
    format_revision = Column(String, nullable=True)
    team_id = Column(String, ForeignKey("quality_teams.id"), nullable=True, index=True)

    # Which slice of time this record covers. `period_key` is the sortable
    # bucket (2026-09-01, 2026-W36, 2026-09, 2026-Q3, 2026) and is what makes
    # "has today's check been done?" answerable.
    period_key = Column(String, nullable=True, index=True)
    period_label = Column(String, nullable=True)
    period_start = Column(DateTime(timezone=True), nullable=True)
    period_end = Column(DateTime(timezone=True), nullable=True)

    # How the record reached the system: filled on screen, or filled on paper
    # and scanned in for OCR. Both are first-class; the client does both today.
    entry_mode = Column(String, nullable=False, default="digital")   # digital | hardcopy

    document_id = Column(String, ForeignKey("documents.id"), nullable=True, index=True)
    workflow_id = Column(String, ForeignKey("approval_workflows.id"), nullable=True, index=True)

    # Optional per-record approval recipients. When absent, the approval
    # workflow uses the people assigned on the format template.
    approval_overrides = Column(Text, nullable=True)

    # Where the record has got to in the chart.
    stage = Column(String, nullable=False, default=STAGE_FILLING, index=True)

    # B5. Null while still being filled; ok or not_ok once evaluated.
    observation_status = Column(String, nullable=True, index=True)

    # B6 condition. Stored rather than computed on the fly so that a list of
    # five hundred records can be filtered and sorted by it in the database.
    # `record_service.refresh_status` is the only writer.
    rag_status = Column(String, nullable=False, default=YELLOW, index=True)

    # What the CFT objected to during the joint review, if anything. The
    # chart's "Final Decision require from CFT" means the person taking that
    # decision must see the CFT's own words, not merely that they answered.
    cft_objection = Column(Text, nullable=True)

    nok_summary = Column(Text, nullable=True)
    nok_flagged_at = Column(DateTime(timezone=True), nullable=True)
    nok_flagged_to = Column(String, ForeignKey("users.id"), nullable=True)
    nok_cleared_at = Column(DateTime(timezone=True), nullable=True)

    # B6: the date the CFT joint review is targeted at.
    cft_target_date = Column(DateTime(timezone=True), nullable=True)

    # How many times the final decision has sent this back to the CFT (the
    # chart's "No" branch). A record on its third re-verification is a process
    # problem, and the number is the only way anyone would notice.
    reverify_count = Column(Integer, nullable=False, default=0)

    filled_by = Column(String, ForeignKey("users.id"), nullable=True)
    filled_at = Column(DateTime(timezone=True), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)

    # B8: where it was finally filed.
    storage_folder_id = Column(String, ForeignKey("document_folders.id"), nullable=True)
    storage_path = Column(String, nullable=True)
    stored_at = Column(DateTime(timezone=True), nullable=True)
    stored_by = Column(String, ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    format = relationship("Format", back_populates="records")
    team = relationship("QualityTeam")
    document = relationship("Document", foreign_keys=[document_id])
    workflow = relationship("ApprovalWorkflow", foreign_keys=[workflow_id])
    filler = relationship("User", foreign_keys=[filled_by])
    storer = relationship("User", foreign_keys=[stored_by])
    flagged_to = relationship("User", foreign_keys=[nok_flagged_to])
    values = relationship(
        "RecordFieldValue",
        back_populates="record",
        cascade="all, delete-orphan",
        order_by="RecordFieldValue.order_index",
    )
    events = relationship(
        "RecordEvent",
        back_populates="record",
        cascade="all, delete-orphan",
        order_by="RecordEvent.created_at",
    )
    actions = relationship(
        "CorrectiveAction",
        back_populates="record",
        cascade="all, delete-orphan",
        order_by="CorrectiveAction.created_at",
    )
    attachments = relationship(
        "RecordAttachment",
        back_populates="record",
        cascade="all, delete-orphan",
        order_by="RecordAttachment.uploaded_at",
    )
    change_requests = relationship(
        "RecordChangeRequest",
        back_populates="record",
        cascade="all, delete-orphan",
        order_by="RecordChangeRequest.raised_at",
    )


class RecordFieldValue(Base):
    """
    One reading on one record, and whether it met its specification.

    The label and the limits are copied here from the FormatField rather than
    read through the relationship. A format revised next year must not silently
    rewrite what last year's record was measured against.
    """
    __tablename__ = "record_field_values"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    record_id = Column(String, ForeignKey("records.id"), nullable=False, index=True)
    field_id = Column(String, ForeignKey("format_fields.id"), nullable=True)
    order_index = Column(Integer, nullable=False, default=0)

    label = Column(String, nullable=False)
    field_type = Column(String, nullable=True)
    unit = Column(String, nullable=True)
    spec_min = Column(Float, nullable=True)
    spec_max = Column(Float, nullable=True)
    spec_text = Column(String, nullable=True)
    # Copied from the FormatField so a filled value finds its place on the form.
    layout_key = Column(String, nullable=True)

    value = Column(Text, nullable=True)
    numeric_value = Column(Float, nullable=True)
    # Null when there is nothing to judge against; otherwise the answer to
    # "was this within specification?", which is what drives ok / N-ok.
    in_spec = Column(Boolean, nullable=True)
    remark = Column(Text, nullable=True)

    record = relationship("Record", back_populates="values")
    # Read-only: what the fill screen needs that is not copied (choices,
    # whether the entry is required, the help text).
    field = relationship("FormatField", viewonly=True)


class RecordEvent(Base):
    """
    The record's own trail, in the language of the process.

    Deliberately separate from WorkflowEvent, which covers only the approval
    chain. Filling, the N-ok flag, re-verification and final storage all happen
    outside the chain and would otherwise leave no trace a user could read.
    """
    __tablename__ = "record_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    record_id = Column(String, ForeignKey("records.id"), nullable=False, index=True)
    actor_id = Column(String, ForeignKey("users.id"), nullable=True)
    kind = Column(String, nullable=False)
    summary = Column(String, nullable=False)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    record = relationship("Record", back_populates="events")
    actor = relationship("User", foreign_keys=[actor_id])


class RecordAttachment(Base):
    """
    A photograph or document supporting one record.

    Distinct from `Record.document_id`, which is the filled sheet itself - the
    evidence the record *is*. These are the things a person adds beside it: a
    photograph of the defect, the gauge's calibration certificate, a supplier's
    test report. There can be any number of them and none is required, which is
    precisely why they cannot live in the single-document slot.

    Held as files beside the record rather than ingested into the document
    repository. A photograph of a scratched housing is not a document anybody
    searches for by name; it is an attachment to one record and it belongs
    where that record can find it.
    """
    __tablename__ = "record_attachments"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    record_id = Column(String, ForeignKey("records.id"), nullable=False, index=True)

    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    mime_type = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)
    # What it is a photograph *of*. Without it an auditor opening a record from
    # two years ago has six images and no idea why any of them is there.
    caption = Column(String, nullable=True)

    uploaded_by = Column(String, ForeignKey("users.id"), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    record = relationship("Record", back_populates="attachments")
    uploader = relationship("User", foreign_keys=[uploaded_by])


class CorrectiveAction(Base):
    """
    What was done about a reading that failed, and whether it is finished.

    A record says a bore was 26.45 against a limit of 25.10. That is the
    finding. What the plant did about it - quarantine the batch, regrind the
    tool, change the setting sheet - is a different fact with a different life:
    it outlives the record, it belongs to somebody by name, it is due on a
    date, and it is either open or closed. Held on the record it came from,
    because an action with no finding behind it is an opinion.

    Nothing here decides anything on its own. Raising one does not alter the
    record's N-ok flag and closing one does not clear it: the chart gives that
    decision to the Overall Process Owner at B5, and an action list must not be
    able to route around a decision the process reserves for a person.
    """
    __tablename__ = "corrective_actions"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    record_id = Column(String, ForeignKey("records.id"), nullable=False, index=True)

    kind = Column(String, nullable=False, default=ACTION_CORRECTIVE, index=True)
    # What is wrong, and what is being done about it. Kept apart because a
    # report of open actions is read for the second and an audit for the first.
    finding = Column(Text, nullable=True)
    action = Column(Text, nullable=False)
    root_cause = Column(Text, nullable=True)

    # Whose it is. Nullable because an action raised in the middle of a shift
    # is often assigned the following morning, and refusing to record it until
    # somebody is named is how it ends up on a sticky note instead.
    owner_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    due_date = Column(DateTime(timezone=True), nullable=True, index=True)

    status = Column(String, nullable=False, default=ACTION_OPEN, index=True)
    closure_note = Column(Text, nullable=True)

    raised_by = Column(String, ForeignKey("users.id"), nullable=True)
    raised_at = Column(DateTime(timezone=True), server_default=func.now())
    closed_by = Column(String, ForeignKey("users.id"), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)

    # When the "this is past its date" alert was raised for this action. Held
    # so the alert fires once rather than on every sweep - see
    # `capa_service.sweep_overdue`.
    overdue_notified_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    record = relationship("Record", back_populates="actions")
    owner = relationship("User", foreign_keys=[owner_id])
    raiser = relationship("User", foreign_keys=[raised_by])
    closer = relationship("User", foreign_keys=[closed_by])


class ChangeRequest(Base):
    """
    A document change request (B9).

    The chart is unambiguous that no format may be altered, and no new format
    generated, without one of these being "followed & approved before
    execution". So this is not a suggestion box: approving a change request is
    the only route by which a Format row is revised or created after go-live.
    """
    __tablename__ = "change_requests"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    number = Column(String, unique=True, nullable=False, index=True)

    kind = Column(String, nullable=False, default="change_existing")
    # change_existing | new_format

    format_id = Column(String, ForeignKey("formats.id"), nullable=True, index=True)
    team_id = Column(String, ForeignKey("quality_teams.id"), nullable=True, index=True)

    title = Column(String, nullable=False)
    reason = Column(Text, nullable=False)
    current_state = Column(Text, nullable=True)
    proposed_change = Column(Text, nullable=False)
    justification = Column(Text, nullable=True)

    raised_by = Column(String, ForeignKey("users.id"), nullable=True)
    raised_at = Column(DateTime(timezone=True), server_default=func.now())

    qms_coordinator_id = Column(String, ForeignKey("users.id"), nullable=True)

    status = Column(String, nullable=False, default="submitted", index=True)
    # submitted | under_review | approved | rejected | implemented

    decided_at = Column(DateTime(timezone=True), nullable=True)
    decided_by = Column(String, ForeignKey("users.id"), nullable=True)
    decision_comment = Column(Text, nullable=True)

    # Set when an approved request has been executed: the revision, or the
    # brand new format, it produced.
    resulting_format_id = Column(String, ForeignKey("formats.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    format = relationship("Format", foreign_keys=[format_id])
    resulting_format = relationship("Format", foreign_keys=[resulting_format_id])
    team = relationship("QualityTeam")
    raiser = relationship("User", foreign_keys=[raised_by])
    coordinator = relationship("User", foreign_keys=[qms_coordinator_id])
    decider = relationship("User", foreign_keys=[decided_by])


class RecordChangeRequest(Base):
    """A controlled request to change information on one filled record."""
    __tablename__ = "record_change_requests"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    number = Column(String, unique=True, nullable=False, index=True)
    record_id = Column(String, ForeignKey("records.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    reason = Column(Text, nullable=False)

    status = Column(String, nullable=False, default="open", index=True)
    raised_by = Column(String, ForeignKey("users.id"), nullable=True)
    raised_at = Column(DateTime(timezone=True), server_default=func.now())
    assigned_to_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    assigned_at = Column(DateTime(timezone=True), nullable=True)

    decided_by = Column(String, ForeignKey("users.id"), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decision_comment = Column(Text, nullable=True)

    implemented_by = Column(String, ForeignKey("users.id"), nullable=True)
    implemented_at = Column(DateTime(timezone=True), nullable=True)
    implementation_note = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    record = relationship("Record", back_populates="change_requests")
    raiser = relationship("User", foreign_keys=[raised_by])
    assignee = relationship("User", foreign_keys=[assigned_to_id])
    decider = relationship("User", foreign_keys=[decided_by])
    implementer = relationship("User", foreign_keys=[implemented_by])


class Notification(Base):
    """
    One "trigger email notification" from the chart, as an auditable row.

    Written before any attempt to send, and kept whether or not a mail server
    is configured. The chart asks for the trigger; an auditor asks for evidence
    the trigger fired. A row here is that evidence even on a site that has not
    given us SMTP credentials yet.
    """
    __tablename__ = "notifications"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    kind = Column(String, nullable=False, index=True)
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=True)

    to_user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    to_email = Column(String, nullable=True)

    related_type = Column(String, nullable=True)     # record | change_request | format
    related_id = Column(String, nullable=True, index=True)

    status = Column(String, nullable=False, default="queued", index=True)
    # queued | sent | failed | skipped   (skipped = no mail server configured)
    error = Column(Text, nullable=True)

    # Whether the person has seen it in the product. The chart asks for email;
    # an in-product list of the same triggers costs nothing extra and means the
    # process still works on a day the mail server is down.
    read_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True), nullable=True)

    recipient = relationship("User", foreign_keys=[to_user_id])


class ApprovalLink(Base):
    """
    A single-use web link that lets one named person answer one approval step.

    The process asks for a trigger email at four points, and an email whose only
    instruction is "sign in and go and find it" is a worse email than no email.
    This is what turns the notification into something actionable: a link the
    recipient opens from their inbox, on whatever device is to hand, that shows
    the record and asks for their decision.

    What it is not is a way around the process. The link is bound to one step,
    one record and one person, it expires, and it is spent the moment a decision
    is recorded through it. Opening somebody else's link shows their name and
    refuses - it does not sign anybody in, and it grants no access to anything
    but the one record it names.

    Deliberately a long random token rather than a signed payload. A signature
    would let a link keep working after the step it belongs to was withdrawn,
    escalated or already answered; a row can be checked against the live state
    of the step every time it is opened, which is what makes revocation real.
    """
    __tablename__ = "approval_links"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    token = Column(String, unique=True, nullable=False, index=True)

    # What it opens. The record is carried alongside the step so the page can
    # be drawn without walking back through the workflow.
    record_id = Column(String, ForeignKey("records.id"), nullable=False, index=True)
    workflow_id = Column(String, nullable=False, index=True)
    step_id = Column(String, nullable=False, index=True)

    # Who it is for. A link is personal: it records the decision against this
    # person, so it must never be treated as a shared password for the step.
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    # Why it was issued, matching the notification kind that carried it.
    purpose = Column(String, nullable=True)

    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    # What was done through it, kept for the audit trail even after the link is
    # spent: an auditor asking "how was this approved" gets "from a link sent to
    # this address, opened from this browser, at this time".
    used_action = Column(String, nullable=True)
    used_from = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    record = relationship("Record", foreign_keys=[record_id])
    user = relationship("User", foreign_keys=[user_id])
