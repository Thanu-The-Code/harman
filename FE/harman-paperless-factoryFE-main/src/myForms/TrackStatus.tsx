import React from "react";
import { Box } from "@mui/material";
import CheckIcon from "@mui/icons-material/Check";
import AccessTimeIcon from "@mui/icons-material/AccessTime";
import PersonOutlineOutlinedIcon from "@mui/icons-material/PersonOutlineOutlined";
import { trackStatusStyles } from "./style";
import RagDot from "../base/status/RagDot";
import { PageLoader } from "../base/feedback";
import type { RecordDetail } from "../api/records.api";
import { useGetWorkflowQuery, type WorkflowStep } from "../api/workflow.api";
import { formatDateTime } from "../utils/date";

type ChipStatus = "Completed" | "In Progress" | "Pending" | "Returned";

const chipClass = (s: ChipStatus) => (s === "Completed" ? "completed" : s === "Pending" ? "pending" : "in-progress");

const STAGE_LABEL: Record<string, string> = {
  po_approval: "Process Owner",
  opo_approval: "Overall Process Owner",
  cft_review: "Quality CFT",
  final_decision: "Final decision",
};

const stepStatus = (s: WorkflowStep): ChipStatus =>
  s.status === "approved" || s.status === "skipped"
    ? "Completed"
    : s.status === "current"
      ? "In Progress"
      : s.status === "rejected" || s.status === "changes_requested"
        ? "Returned"
        : "Pending";

interface TimelineRow {
  id: string;
  step: number;
  title: string;
  role: string;
  people: string;
  status: ChipStatus;
  notes: string[];
  by: string;
  at: string;
}

/** Where a record is in its approval chain (record process steps 4–10). */
const TrackStatus: React.FC<{ record: RecordDetail }> = ({ record }) => {
  const { data: workflow, isLoading } = useGetWorkflowQuery(record.workflow_id ?? "", { skip: !record.workflow_id });
  if (record.workflow_id && isLoading) return <PageLoader label="Loading the approval…" />;

  const rows: TimelineRow[] = workflow
    ? workflow.steps.map((s) => ({
        id: s.id,
        step: s.order,
        title: s.name,
        role: (s.qms_stage && STAGE_LABEL[s.qms_stage]) || s.role || "Approver",
        people: s.assignees.map((a) => a.name).join(", "),
        status: stepStatus(s),
        notes: [
          s.comment ? `Comment: ${s.comment}` : "",
          s.reason ? `Reason: ${s.reason}` : "",
          s.approval_mode === "all" && s.status === "current" && s.outstanding.length
            ? `Waiting for: ${s.outstanding.map((o) => o.name).join(", ")}`
            : "",
          s.overdue ? "Overdue" : "",
        ].filter(Boolean),
        by: s.decided_by?.name ?? (s.status === "current" ? "Waiting" : "—"),
        at: s.decided_at ? formatDateTime(s.decided_at) : s.due_date ? `due ${formatDateTime(s.due_date)}` : "",
      }))
    : record.route.map((s) => ({
        // not submitted yet: the route it will take
        id: String(s.order),
        step: s.order,
        title: s.name,
        role: (s.stage && STAGE_LABEL[s.stage]) || "Approver",
        people: s.people.map((p) => p.name).join(", ") || "Chosen when submitting",
        status: "Pending" as ChipStatus,
        notes: [s.requires_signature ? "Signed approval" : "", s.mode === "all" ? "Every member answers" : ""].filter(Boolean),
        by: "—",
        at: `${s.days} day${s.days === 1 ? "" : "s"}`,
      }));

  const summaryStatus: ChipStatus =
    record.stage === "stored" ? "Completed" : record.stage === "filling" ? "Pending" : "In Progress";

  const summary: [string, React.ReactNode][] = [
    ["Record", <span className="summary-link">{record.number}</span>],
    ["Tracking", <RagDot rag={record.rag} label={record.rag_label} showLabel />],
    ["Stage", <span className="summary-value">{record.stage_label}</span>],
    ["Priority", <span className="priority-chip">{workflow?.priority ?? "—"}</span>],
    ["Assigned to", <span className="summary-value">{record.awaiting?.people.map((p) => p.name).join(", ") || "—"}</span>],
    ["This step needs", <span className="summary-value">{record.awaiting?.step ?? "—"}</span>],
    ["Started by", <span className="summary-value">{record.filled_by?.name ?? "—"}</span>],
    ["Submitted", <span className="summary-value">{formatDateTime(record.submitted_at)}</span>],
    ["Needed by", <span className="summary-value">{formatDateTime(workflow?.due_date)}</span>],
    ["This step due", <span className="summary-value">{formatDateTime(record.awaiting?.due)}</span>],
    ["CFT target", <span className="summary-value">{formatDateTime(record.cft_target_date)}</span>],
    ["Filed in", <span className="summary-value">{record.storage_path ?? record.storage_preview}</span>],
  ];

  return (
    <Box className="track-status" sx={trackStatusStyles}>
      <div className="track-grid">
        <div className="track-card">
          <div className="track-card-head">
            <span>This Approval</span>
            <span className={`status-chip ${chipClass(summaryStatus)}`}>{record.stage_label}</span>
          </div>
          <div className="summary-list">
            {summary.map(([label, value]) => (
              <div className="summary-row" key={label}>
                <span className="summary-label">{label}</span>
                {value}
              </div>
            ))}
          </div>
          {record.nok_open && (
            <p className="track-card-caption" style={{ color: "#b91c1c" }}>
              N-OK flagged to {record.nok_flagged_to?.name ?? "the Overall Process Owner"}: {record.nok_summary}
            </p>
          )}
          {record.cft_objection && (
            <p className="track-card-caption" style={{ color: "#b91c1c" }}>
              CFT objection: {record.cft_objection}
            </p>
          )}
        </div>

        <div className="track-card">
          <div className="track-card-head" style={{ display: "block" }}>
            Approval Timeline
            <p className="track-card-caption">
              {workflow
                ? "Each step waits for the one above it."
                : "Not submitted yet — this is the route the record will take."}
            </p>
          </div>
          <div className="timeline">
            {rows.map((step) => (
              <div className="timeline-item" key={step.id}>
                <span className={`timeline-marker ${chipClass(step.status)}`}>
                  {step.status === "Completed" ? <CheckIcon /> : <AccessTimeIcon />}
                </span>
                <span className="step-chip">Step {step.step}</span>
                <div className="step-card">
                  <div className="step-top">
                    <div>
                      <div className="step-title">{step.title}</div>
                      <div className="step-role">
                        <b>{step.role}</b> · {step.people}
                      </div>
                    </div>
                    <span className={`status-chip ${chipClass(step.status)}`}>{step.status}</span>
                  </div>
                  {step.notes.length > 0 && (
                    <ul className="step-notes">
                      {step.notes.map((n) => (
                        <li key={n}>{n}</li>
                      ))}
                    </ul>
                  )}
                  <div className="step-meta">
                    <span>
                      <PersonOutlineOutlinedIcon /> {step.by}
                    </span>
                    {step.at && (
                      <span>
                        <AccessTimeIcon /> {step.at}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </Box>
  );
};

export default TrackStatus;
