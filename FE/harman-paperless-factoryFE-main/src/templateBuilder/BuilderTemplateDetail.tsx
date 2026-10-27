import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Box, Button } from "@mui/material";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import { toast } from "react-toastify";
import { builderTemplateDetailStyles } from "./style";
import { approvalReviewStyles } from "../myApprovals/style";
import PageHeader from "../base/pageHeader";
import InfoCard from "../base/info";
import ApprovalTimeline, { type TimelineStep } from "../myApprovals/ApprovalTimeline";
import CustomDialog from "../base/dialog/CustomDialog";
import CustomTextArea from "../base/dialog/CustomTextarea";
import { ErrorState, PageLoader } from "../base/feedback";
import { useMeQuery } from "../api/auth.api";
import {
  formatStatusLabel,
  useDecideFormatApprovalMutation,
  useGetFormatQuery,
  useWithdrawFormatMutation,
  type FormatDetail,
  type FormatReview,
} from "../api/formats.api";
import { getApiErrorMessage } from "../api/errors";
import { useAuthedObjectUrl } from "../hooks/useAuthedObjectUrl";
import { formatDate, formatDateTime } from "../utils/date";

const SummaryColumn = ({ rows }: { rows: [string, string][] }) => (
  <div>
    {rows.map(([label, value]) => (
      <div className="summary-row" key={label}>
        <span className="summary-label">{label}</span>
        <span className="summary-value">{value || "—"}</span>
      </div>
    ))}
  </div>
);

/** The release review's steps, drawn with the shared approval timeline. */
const reviewTimeline = (review: FormatReview): TimelineStep[] =>
  review.steps.map((step, index) => {
    const rejected = step.decisions.some((d) => d.decision === "reject");
    const done =
      review.status === "approved" || (review.current_step !== undefined && index < review.current_step && !rejected);
    const current = review.status === "pending" && index === review.current_step;
    const last = step.decisions[step.decisions.length - 1];
    return {
      id: `${review.id}-${index}`,
      step: index + 1,
      title: step.name,
      role: step.reviewers.join(", ") || "—",
      department: step.mode === "all" ? "every reviewer approves" : "any one reviewer approves",
      status: rejected ? "Changes requested" : done ? "Completed" : current ? "In Progress" : "Pending",
      notes: step.decisions
        .map((d) => `${d.reviewer}: ${d.decision === "approve" ? "approved" : "changes requested"}${d.comment ? ` — ${d.comment}` : ""}`)
        .filter(Boolean),
      by: last?.reviewer ?? (current ? "Waiting" : ""),
      at: last?.at ? formatDateTime(last.at) : undefined,
    };
  });

const people = (list: { name: string }[]) => list.map((p) => p.name).join(", ");

const Preview = ({ format }: { format: FormatDetail }) => {
  const blank = useAuthedObjectUrl(format.has_blank ? `api/formats/${format.id}/blank?inline=true` : null);
  if (format.has_blank) {
    if (blank.loading) return <PageLoader label="Loading the blank form…" />;
    if (blank.url) return <iframe title="Blank form" src={blank.url} />;
    return <ErrorState message={blank.error ?? "The blank form could not be shown."} />;
  }
  // no blank attached: list what the form records
  return (
    <div className="doc-page">
      <div className="doc-brand">
        <span className="doc-brand-logo" /> Paperless Factory
      </div>
      <h3 className="doc-heading">{format.title}</h3>
      {format.fields.length === 0 ? (
        <p style={{ fontSize: 12, color: "#6b7280" }}>This template does not record anything yet.</p>
      ) : (
        <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
          <tbody>
            {format.fields.map((f) => (
              <tr key={f.id} style={{ borderBottom: "1px solid #eef0f3" }}>
                <td style={{ padding: "6px 4px" }}>{f.label}</td>
                <td style={{ padding: "6px 4px", color: "#6b7280" }}>{f.field_type}</td>
                <td style={{ padding: "6px 4px", color: "#0f766e" }}>{f.spec_label}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};

const BuilderTemplateDetail = () => {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: me } = useMeQuery();
  const { data: format, isLoading, isError, error, refetch } = useGetFormatQuery(id);
  const [decide, { isLoading: deciding }] = useDecideFormatApprovalMutation();
  const [withdraw, { isLoading: withdrawing }] = useWithdrawFormatMutation();
  const [dialog, setDialog] = useState<"approve" | "reject" | "withdraw" | null>(null);
  const [comment, setComment] = useState("");

  if (isLoading) return <PageLoader label="Loading template…" />;
  if (isError || !format) {
    // a template that is not there (or no longer yours to see) will not appear on a retry
    const missing = !!error && "status" in error && error.status === 404;
    return <ErrorState message={(error && "message" in error && error.message) || "Template not found."} onRetry={missing ? undefined : refetch} />;
  }

  const isAdmin = !!me?.is_admin;
  const review = format.approval;
  const status = formatStatusLabel(format.status, format.approval_status);
  const closeDialog = () => {
    setDialog(null);
    setComment("");
  };

  const handleDecision = async (decision: "approve" | "reject") => {
    try {
      const result = await decide({ id: format.id, decision, comment: comment.trim() || undefined }).unwrap();
      toast.success(
        decision === "reject"
          ? "Rejected. The template goes back to the author with your comment."
          : result.format.status === "active"
            ? "Approved. The template is now released."
            : "Approved. It moves to the next review step.",
      );
      closeDialog();
      // a reviewer who is not an administrator no longer sees the draft once it is decided
      if (!isAdmin) navigate("/my-approvals");
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Could not record your decision."));
    }
  };

  const handleWithdraw = async () => {
    try {
      await withdraw(format.id).unwrap();
      toast.success(format.status === "draft" ? "Draft discarded." : "Template withdrawn from use.");
      closeDialog();
      navigate("/builder");
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Could not withdraw the template."));
    }
  };

  const summaryLeft: [string, string][] = [
    ["Code", format.code],
    ["Title", format.title],
    ["Team", format.team?.name ?? ""],
    ["Frequency", format.frequency_label],
    ["Revision", format.revision],
    ["Status", status],
  ];
  const summaryRight: [string, string][] = [
    ["Process Owner", format.process_owner?.name ?? "Chosen at submission"],
    ["Overall P. Owner", format.overall_process_owner?.name ?? "Chosen at submission"],
    ["CFT members", people(format.cft_members) || "Chosen at submission"],
    ["QMS Coordinator", format.qms_coordinator?.name ?? ""],
    ["Work instruction", format.work_instruction_ref ?? ""],
    ["Filed in", format.storage_preview],
  ];

  return (
    <Box className="approval-review-page builder-template-detail" sx={approvalReviewStyles}>
      <Box sx={builderTemplateDetailStyles}>
        <PageHeader
          className="builder-detail-header"
          title={`${format.code} · ${format.title}`}
          subtitle={`Rev ${format.revision} · ${status} · created ${formatDate(format.created_at)}`}
          onBack={() => navigate(isAdmin ? "/builder" : "/my-approvals")}
        />

        <div className="review-content">
          <div className="review-col">
            <InfoCard title="Template Summary">
              <div className="summary-grid">
                <SummaryColumn rows={summaryLeft} />
                <SummaryColumn rows={summaryRight} />
              </div>
              {format.status === "draft" && format.readiness.length > 0 && (
                <div style={{ marginTop: 10, fontSize: 12, color: "#92400e" }}>
                  <strong>Before release:</strong>
                  <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                    {format.readiness.map((p) => (
                      <li key={p}>{p}</li>
                    ))}
                  </ul>
                </div>
              )}
            </InfoCard>

            <InfoCard title="Document Preview" flush>
              <div className="doc-head">
                <div className="doc-title">
                  <span>
                    {format.field_count} recorded {format.field_count === 1 ? "entry" : "entries"}
                    {format.record_count ? ` · ${format.record_count} records filled` : ""}
                  </span>
                </div>
                {isAdmin && (
                  <Button
                    className="open-btn"
                    startIcon={<OpenInNewIcon fontSize="small" />}
                    onClick={() => navigate(`/builder/${format.id}/build?format_id=${format.id}`)}
                  >
                    Open in designer
                  </Button>
                )}
              </div>
              <div className="doc-preview">
                <Preview format={format} />
              </div>
            </InfoCard>
          </div>

          <div className="review-col">
            <InfoCard title="Approval Details" flush>
              <div className="detail-table">
                <div className="detail-row">
                  <div className="detail-label">Review status</div>
                  <div className="detail-value highlight">
                    {review.status === "none" ? "Not sent for approval" : review.status}
                  </div>
                </div>
                <div className="detail-row">
                  <div className="detail-label">Submitted by</div>
                  <div className="detail-value">{review.submitted_by?.name ?? "—"}</div>
                </div>
                <div className="detail-row">
                  <div className="detail-label">Submitted on</div>
                  <div className="detail-value">{formatDateTime(review.submitted_at)}</div>
                </div>
                <div className="detail-row">
                  <div className="detail-label">Priority</div>
                  <div className="detail-value accent">{review.priority ?? "—"}</div>
                </div>
              </div>
            </InfoCard>

            <InfoCard title="Approval Timeline" flush>
              {review.steps.length ? (
                <ApprovalTimeline steps={reviewTimeline(review)} />
              ) : (
                <p style={{ padding: 12, fontSize: 12, color: "#6b7280" }}>No release review yet.</p>
              )}
            </InfoCard>

            {isAdmin && format.versions && format.versions.length > 1 && (
              <InfoCard title="Revisions">
                {format.versions.map((v) => (
                  <div className="summary-row" key={v.id}>
                    <span className="summary-label">Rev {v.revision}</span>
                    <span className="summary-value">
                      {formatStatusLabel(v.status, v.approval_status)}
                      {v.effective_date ? ` · effective ${formatDate(v.effective_date)}` : ""}
                    </span>
                  </div>
                ))}
              </InfoCard>
            )}
          </div>
        </div>

        <div className="action-bar builder-detail-actions">
          {review.can_act ? (
            <>
              <div className="action-info">
                <div>
                  <div className="action-info-title">Your review is requested</div>
                  <div className="action-info-text">Approve to release (or pass to the next step), or reject with a comment.</div>
                </div>
              </div>
              <div className="action-buttons">
                <Button className="action-btn reject-btn" onClick={() => setDialog("reject")}>
                  Reject
                </Button>
                <Button className="action-btn approve-btn" variant="contained" onClick={() => setDialog("approve")}>
                  Approve
                </Button>
              </div>
            </>
          ) : (
            isAdmin && (
              <div className="action-buttons">
                {["draft", "active"].includes(format.status) && (
                  <Button className="action-btn builder-delete-btn" onClick={() => setDialog("withdraw")}>
                    {format.status === "draft" ? "Discard draft" : "Withdraw"}
                  </Button>
                )}
                {format.status === "draft" && (
                  <Button
                    className="action-btn builder-edit-btn"
                    variant="contained"
                    onClick={() => navigate(`/builder/${format.id}/build?format_id=${format.id}`)}
                  >
                    Edit
                  </Button>
                )}
              </div>
            )
          )}
        </div>
      </Box>

      <CustomDialog
        open={dialog === "approve"}
        onClose={closeDialog}
        onConfirm={() => handleDecision("approve")}
        title="Approve template"
        subtitle={<>You are approving <b>{format.code}</b> rev {format.revision}.</>}
        confirmText={deciding ? "Saving…" : "Approve"}
        confirmDisabled={deciding}
      >
        <CustomTextArea label="Comment" optional value={comment} onChange={setComment} placeholder="Recorded on the review" rows={4} />
      </CustomDialog>
      <CustomDialog
        open={dialog === "reject"}
        onClose={closeDialog}
        onConfirm={() => handleDecision("reject")}
        title="Reject template"
        subtitle="It goes back to the author as a draft with your comment."
        confirmText={deciding ? "Saving…" : "Reject"}
        confirmDisabled={deciding || !comment.trim()}
      >
        <CustomTextArea label="What needs to change?" value={comment} onChange={setComment} placeholder="Required" rows={5} />
      </CustomDialog>
      <CustomDialog
        open={dialog === "withdraw"}
        onClose={closeDialog}
        onConfirm={handleWithdraw}
        title={format.status === "draft" ? "Discard this draft?" : "Withdraw this template?"}
        subtitle={
          format.status === "draft"
            ? "The draft is withdrawn and no longer listed. Nothing filled against it exists yet."
            : "It can no longer be called. Records already filled against it are kept."
        }
        confirmText={withdrawing ? "Working…" : format.status === "draft" ? "Discard" : "Withdraw"}
        confirmDisabled={withdrawing}
      >
        <span />
      </CustomDialog>
    </Box>
  );
};

export default BuilderTemplateDetail;
