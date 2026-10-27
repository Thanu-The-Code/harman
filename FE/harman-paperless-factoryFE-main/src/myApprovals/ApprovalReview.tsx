import { useState, type ReactNode } from "react";
import ReadingsTable from "../base/readings/ReadingsTable";
import { useNavigate, useParams } from "react-router-dom";
import { Box, Button } from "@mui/material";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import { toast } from "react-toastify";
import { approvalReviewStyles } from "./style";
import PageHeader from "../base/pageHeader";
import InfoCard from "../base/info";
import RagDot from "../base/status/RagDot";
import { ErrorState, PageLoader } from "../base/feedback";
import { retryUnlessFinal } from "../base/feedback/retry";
import ApprovalTimeline, { type TimelineStep } from "./ApprovalTimeline";
import { DecisionDialog, type DecisionResult } from "./ActionDialogs";
import { useMeQuery } from "../api/auth.api";
import { useClearNokMutation, useGetRecordQuery, useStoreRecordMutation, type RecordDetail } from "../api/records.api";
import { useDecideStepMutation, useGetWorkflowQuery, type Workflow, type WorkflowStep } from "../api/workflow.api";
import { getApiErrorMessage } from "../api/errors";
import { useAuthedObjectUrl } from "../hooks/useAuthedObjectUrl";
import { openAuthedFile } from "../utils/openAuthedFile";
import { formatDate, formatDateTime } from "../utils/date";

const STAGE_LABEL: Record<string, string> = {
  po_approval: "Process Owner",
  opo_approval: "Overall Process Owner",
  cft_review: "Quality CFT",
  final_decision: "Final decision",
};

interface StepActions {
  positive: string;
  negative: string;
  positiveTitle: string;
  negativeTitle: string;
  negativeLabel: string;
  negativeHint: string;
  positiveDone: string;
  negativeDone: string;
}

/** What the two answers mean at each point of the record process. */
const ACTIONS: Record<string, StepActions> = {
  po_approval: {
    positive: "Approve",
    negative: "Return for correction",
    positiveTitle: "Approve and sign",
    negativeTitle: "Return for correction",
    negativeLabel: "What has to be corrected?",
    negativeHint: "The record goes back to the person who filled it, with your note.",
    positiveDone: "Approved and signed. The Overall Process Owner has been notified.",
    negativeDone: "Returned for correction.",
  },
  opo_approval: {
    positive: "Approve",
    negative: "Return for correction",
    positiveTitle: "Approve and sign",
    negativeTitle: "Return for correction",
    negativeLabel: "What has to be corrected?",
    negativeHint: "The record goes back to the person who filled it, with your note.",
    positiveDone: "Approved and signed. The CFT joint review is open.",
    negativeDone: "Returned for correction.",
  },
  cft_review: {
    positive: "Agree",
    negative: "Object",
    positiveTitle: "Agree with the record",
    negativeTitle: "Object",
    negativeLabel: "Your objection",
    negativeHint: "Your objection is carried to the final decision; the review closes when every member has answered.",
    positiveDone: "Your agreement is recorded.",
    negativeDone: "Your objection is recorded.",
  },
  final_decision: {
    positive: "Approve",
    negative: "Send back to CFT",
    positiveTitle: "Final decision: approve and sign",
    negativeTitle: "Send back to the CFT",
    negativeLabel: "Why must the CFT look again?",
    negativeHint: "The record goes back to the CFT for re-verification and turns red.",
    positiveDone: "Final decision recorded. The record can now be filed.",
    negativeDone: "Sent back to the CFT for re-verification.",
  },
};

const DEFAULT_ACTIONS: StepActions = {
  positive: "Approve",
  negative: "Reject",
  positiveTitle: "Approve",
  negativeTitle: "Reject",
  negativeLabel: "Why are you rejecting it?",
  negativeHint: "",
  positiveDone: "Approved.",
  negativeDone: "Rejected.",
};

const timeline = (workflow: Workflow): TimelineStep[] =>
  workflow.steps.map((s) => ({
    id: s.id,
    step: s.order,
    title: s.name,
    role: (s.qms_stage && STAGE_LABEL[s.qms_stage]) || s.role || "Approver",
    department: s.assignees.map((a) => a.name).join(", ") || "—",
    status: s.status === "approved" || s.status === "skipped" ? "Completed" : s.status === "current" ? "In Progress" : "Pending",
    notes: [
      s.comment ? `Comment: ${s.comment}` : "",
      s.reason ? `Reason: ${s.reason}` : "",
      s.signature ? `Signed by ${s.signature.name}` : "",
      s.status === "current" && s.approval_mode === "all" && s.outstanding.length
        ? `Waiting for: ${s.outstanding.map((o) => o.name).join(", ")}`
        : "",
      s.overdue ? "Overdue" : "",
    ].filter(Boolean),
    by: s.decided_by?.name ?? (s.status === "current" ? "Waiting" : "—"),
    at: s.decided_at ? formatDateTime(s.decided_at) : s.due_date ? `due ${formatDateTime(s.due_date)}` : undefined,
  }));

type Dialog = "positive" | "negative" | "clear" | "store" | null;

const SummaryColumn = ({ rows }: { rows: [string, ReactNode][] }) => (
  <div>
    {rows.map(([label, value]) => (
      <div className="summary-row" key={label}>
        <span className="summary-label">{label}</span>
        <span className="summary-value">{value || "—"}</span>
      </div>
    ))}
  </div>
);

const Preview = ({ record, workflow }: { record: RecordDetail; workflow?: Workflow }) => {
  // the PDF with the signatures so far, else the document as filed
  const stamped = useAuthedObjectUrl(workflow ? `api/signatures/${workflow.id}/preview` : null);
  const plain = useAuthedObjectUrl(
    (!workflow || stamped.error) && record.document_id ? `api/documents/${record.document_id}/file` : null,
  );
  const url = stamped.url ?? plain.url;
  if (stamped.loading || plain.loading) return <PageLoader label="Loading the document…" />;
  if (url) return <iframe title="Record document" src={url} />;
  return <ErrorState message="No document is attached to this record yet." />;
};

const Review = ({ record, workflow }: { record: RecordDetail; workflow?: Workflow }) => {
  const navigate = useNavigate();
  const { data: me } = useMeQuery();
  const [decide, { isLoading: deciding }] = useDecideStepMutation();
  const [clearNok, { isLoading: clearing }] = useClearNokMutation();
  const [storeRecord, { isLoading: storing }] = useStoreRecordMutation();
  const [dialog, setDialog] = useState<Dialog>(null);

  const current: WorkflowStep | undefined = workflow?.steps.find((s) => s.status === "current");
  const actions = (current?.qms_stage && ACTIONS[current.qms_stage]) || DEFAULT_ACTIONS;
  const canAct = !!current?.can_act;
  const title = `${record.format.title}`;

  const answer = async (positive: boolean, { note, signature }: DecisionResult) => {
    if (!workflow || !current) return;
    try {
      await decide({
        workflowId: workflow.id,
        stepId: current.id,
        recordId: record.id,
        action: positive ? "approve" : "reject",
        comment: note,
        reason: positive ? "" : note,
        signature:
          positive && current.requires_signature && signature
            ? { dataUrl: signature.dataUrl, method: signature.method, name: me?.full_name ?? me?.username, designation: me?.job_title ?? undefined }
            : undefined,
      }).unwrap();
      toast.success(positive ? actions.positiveDone : actions.negativeDone);
      setDialog(null);
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Could not record your decision."));
    }
  };

  const onClearNok = async ({ note }: DecisionResult) => {
    try {
      await clearNok({ id: record.id, note }).unwrap();
      toast.success("N-OK flag closed.");
      setDialog(null);
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Could not close the N-OK flag."));
    }
  };

  const onStore = async () => {
    try {
      const filed = await storeRecord(record.id).unwrap();
      toast.success(`Filed in ${filed.storage_path}`);
      setDialog(null);
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Could not file the record."));
    }
  };

  const summaryLeft: [string, ReactNode][] = [
    ["Format", `${record.format.code} · rev ${record.format_revision}`],
    ["Team", record.team?.name],
    ["Period", record.period_label],
    ["Filled by", record.filled_by?.name],
    ["Filled on", formatDateTime(record.filled_at)],
  ];
  const summaryRight: [string, ReactNode][] = [
    ["Result", record.observation_status === "not_ok" ? "N-OK" : record.observation_status === "ok" ? "OK" : "—"],
    ["Tracking", <RagDot rag={record.rag} label={record.rag_label} showLabel />],
    ["Stage", record.stage_label],
    ["Entries", `${record.values.filter((v) => (v.value ?? "").trim()).length} / ${record.values.length}`],
    ["CFT target", formatDate(record.cft_target_date)],
  ];

  const blocked = current && !canAct ? current.blocked_reason : null;
  const anything = canAct || record.can.clear_nok || record.can.store;

  return (
    <>
      <PageHeader
        title={title}
        subtitle={`${record.number} · ${record.period_label} · submitted ${formatDate(record.submitted_at)}`}
        onBack={() => navigate("/my-approvals")}
      />

      <div className="review-content">
        <div className="review-col">
          {(record.nok_open || record.cft_objection || record.reverify_count > 0 || record.missing.length > 0) && (
            <div className="review-alert" role="alert">
              {record.missing.length > 0 && (
                // blanks do not stop a submission (B3), so the approver is told what they are signing
                <div>
                  <strong>{record.missing.length} required {record.missing.length === 1 ? "entry is" : "entries are"} blank:</strong>{" "}
                  {record.missing.slice(0, 6).join("; ")}
                  {record.missing.length > 6 ? ` and ${record.missing.length - 6} more` : ""}.
                </div>
              )}
              {record.nok_open && (
                <div>
                  <strong>N-OK flagged</strong> to {record.nok_flagged_to?.name ?? "the Overall Process Owner"}: {record.nok_summary}
                </div>
              )}
              {record.cft_objection && (
                <div>
                  <strong>CFT objection:</strong> {record.cft_objection}
                </div>
              )}
              {record.reverify_count > 0 && <div>Sent back for re-verification {record.reverify_count}×.</div>}
            </div>
          )}

          <InfoCard title="Document Summary">
            <div className="summary-grid">
              <SummaryColumn rows={summaryLeft} />
              <SummaryColumn rows={summaryRight} />
            </div>
          </InfoCard>

          <InfoCard title="Readings" flush>
            <ReadingsTable readings={[...record.values].sort((a, b) => a.order - b.order)} showSpec />
          </InfoCard>

          <InfoCard title="Document Preview" flush>
            <div className="doc-head">
              <div className="doc-title">
                <span>{record.number}</span>
              </div>
              {record.document_id && (
                <Button
                  className="open-btn"
                  startIcon={<OpenInNewIcon fontSize="small" />}
                  onClick={() =>
                    openAuthedFile(workflow ? `api/signatures/${workflow.id}/preview` : `api/documents/${record.document_id}/file`)
                  }
                >
                  View/ Open Document
                </Button>
              )}
            </div>
            <div className="doc-preview">
              <Preview record={record} workflow={workflow} />
            </div>
          </InfoCard>
        </div>

        <div className="review-col">
          <InfoCard title="Approval Details" flush>
            <div className="detail-table">
              <div className="detail-row">
                <div className="detail-label">Currently assigned to</div>
                <div className="detail-value highlight">
                  {record.awaiting?.people.map((p) => p.name).join(", ") || (record.stage === "stored" ? "Filed" : "—")}
                </div>
              </div>
              <div className="detail-row">
                <div className="detail-label">This step</div>
                <div className="detail-value">{record.awaiting?.step ?? record.stage_label}</div>
              </div>
              <div className="detail-row">
                <div className="detail-label">Submitted by</div>
                <div className="detail-value">{workflow?.created_by?.name ?? record.filled_by?.name ?? "—"}</div>
              </div>
              <div className="detail-row">
                <div className="detail-label">Step due</div>
                <div className="detail-value">
                  {formatDateTime(record.awaiting?.due)}
                  {record.awaiting?.overdue ? " · overdue" : ""}
                </div>
              </div>
              <div className="detail-row">
                <div className="detail-label">Priority</div>
                <div className="detail-value accent">{workflow?.priority ?? "—"}</div>
              </div>
            </div>
          </InfoCard>

          <InfoCard title="Approval Timeline" flush>
            {workflow ? <ApprovalTimeline steps={timeline(workflow)} /> : <p className="muted" style={{ padding: 12 }}>Not in approval.</p>}
          </InfoCard>
        </div>
      </div>

      <div className="action-bar">
        <div className="action-info">
          <span className="action-info-icon">
            <InfoOutlinedIcon />
          </span>
          <div>
            <div className="action-info-title">{anything ? "Your action is required" : "No action needed from you"}</div>
            <div className="action-info-text">
              {canAct
                ? current?.requires_signature
                  ? "Review the readings and the document, then answer. This step is signed."
                  : "Review the readings and the document, then answer."
                : blocked ||
                  (record.can.store
                    ? "Every step is approved. File the record to finish."
                    : record.can.clear_nok
                      ? "Close the N-OK flag once the observations have been dealt with."
                      : `This record is at: ${record.stage_label}.`)}
            </div>
          </div>
        </div>
        <div className="action-buttons">
          {record.can.clear_nok && (
            <Button className="action-btn change-btn" onClick={() => setDialog("clear")}>
              Clear N-OK flag
            </Button>
          )}
          {canAct && (
            <>
              <Button className="action-btn reject-btn" onClick={() => setDialog("negative")}>
                {actions.negative}
              </Button>
              <Button className="action-btn approve-btn" variant="contained" onClick={() => setDialog("positive")}>
                {actions.positive}
              </Button>
            </>
          )}
          {record.can.store && (
            <Button className="action-btn approve-btn" variant="contained" onClick={() => setDialog("store")}>
              File record
            </Button>
          )}
        </div>
      </div>

      {dialog === "positive" && current && (
        <DecisionDialog
          open
          onClose={() => setDialog(null)}
          onConfirm={(r) => answer(true, r)}
          title={actions.positiveTitle}
          subtitle={
            <>
              {current.name} for <b>{record.number}</b>.
            </>
          }
          confirmText={actions.positive}
          noteLabel="Comment"
          requiresSignature={current.requires_signature}
          signerName={me?.full_name ?? me?.username}
          busy={deciding}
        />
      )}
      {dialog === "negative" && current && (
        <DecisionDialog
          open
          onClose={() => setDialog(null)}
          onConfirm={(r) => answer(false, r)}
          title={actions.negativeTitle}
          subtitle={actions.negativeHint}
          confirmText={actions.negative}
          noteLabel={actions.negativeLabel}
          noteRequired
          busy={deciding}
        />
      )}
      {dialog === "clear" && (
        <DecisionDialog
          open
          onClose={() => setDialog(null)}
          onConfirm={onClearNok}
          title="Close the N-OK flag"
          subtitle="Say what was done about the out-of-specification observations."
          confirmText="Close flag"
          noteLabel="Action taken"
          noteRequired
          busy={clearing}
        />
      )}
      {dialog === "store" && (
        <DecisionDialog
          open
          onClose={() => setDialog(null)}
          onConfirm={onStore}
          title="File the record"
          subtitle={
            <>
              It is filed as a completed quality record in <b>{record.storage_preview}</b>.
            </>
          }
          confirmText="File record"
          noteLabel="Note"
          busy={storing}
        />
      )}
    </>
  );
};

/** `/my-approvals/:id` — review one record and answer its current step. */
const ApprovalReviewPage = () => {
  const { id = "" } = useParams<{ id: string }>();
  const { data: record, isLoading, isError, error, refetch } = useGetRecordQuery(id);
  const { data: workflow, isLoading: loadingWf } = useGetWorkflowQuery(record?.workflow_id ?? "", {
    skip: !record?.workflow_id,
  });

  return (
    <Box className="approval-review-page" sx={approvalReviewStyles}>
      {isLoading || (record?.workflow_id && loadingWf) ? (
        <PageLoader label="Loading the record…" />
      ) : isError || !record ? (
        <ErrorState message={(error && "message" in error && error.message) || "Record not found."} onRetry={retryUnlessFinal(error, refetch)} />
      ) : (
        <Review record={record} workflow={workflow} />
      )}
    </Box>
  );
};

export default ApprovalReviewPage;
