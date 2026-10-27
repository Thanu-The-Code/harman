import { Box, Button } from "@mui/material";
import ReadingsTable from "../base/readings/ReadingsTable";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import DownloadOutlinedIcon from "@mui/icons-material/DownloadOutlined";
import { approvalReviewStyles } from "../myApprovals/style";
import PageHeader from "../base/pageHeader";
import InfoCard from "../base/info";
import { ErrorState, PageLoader } from "../base/feedback";
import { retryUnlessFinal } from "../base/feedback/retry";
import ApprovalTimeline, { type TimelineStep } from "../myApprovals/ApprovalTimeline";
import { useRepositorySummaryQuery, useRepositoryTimelineQuery, type RecordTimeline } from "../api/repository.api";
import { useAuthedObjectUrl } from "../hooks/useAuthedObjectUrl";
import { downloadAuthedFile, openAuthedFile } from "../utils/openAuthedFile";
import { formatDateTime } from "../utils/date";

const STAGE_LABEL: Record<string, string> = {
  po_approval: "Process Owner",
  opo_approval: "Overall Process Owner",
  cft_review: "Quality CFT",
  final_decision: "Final decision",
};

const toTimeline = (t: RecordTimeline): TimelineStep[] =>
  t.steps.map((s) => ({
    id: s.id,
    step: s.order,
    title: s.name,
    role: (s.stage && STAGE_LABEL[s.stage]) || "Approver",
    department: s.assigned_to.map((p) => p.name).join(", ") || "—",
    status: s.status === "approved" ? "Completed" : s.status === "current" ? "In Progress" : "Pending",
    notes: [
      s.signature ? `Signed by ${s.signature.name}${s.signature.designation ? `, ${s.signature.designation}` : ""}` : "",
      s.comment ? `Comment: ${s.comment}` : "",
      s.reason ? `Reason: ${s.reason}` : "",
    ].filter(Boolean),
    by: s.decided_by?.name ?? "—",
    at: s.decided_at ? formatDateTime(s.decided_at) : undefined,
  }));

/** A filed record: what was recorded, who signed it, and the document itself. */
const RecordFileDetail = ({ recordId, onBack }: { recordId: string; onBack: () => void }) => {
  const { data: summary, isLoading, isError, error, refetch } = useRepositorySummaryQuery(recordId);
  const { data: timeline } = useRepositoryTimelineQuery(recordId);
  const preview = useAuthedObjectUrl(
    timeline?.workflow ? `api/signatures/${timeline.workflow.id}/preview` : summary?.document ? summary.document.file_url : null,
  );

  if (isLoading) return <PageLoader label="Loading the record…" />;
  if (isError || !summary) {
    return <ErrorState message={(error && "message" in error && error.message) || "Record not found."} onRetry={retryUnlessFinal(error, refetch)} />;
  }
  const s = summary.summary;
  const rows: [string, string][] = [
    ["Format", `${s.code}${s.revision ? ` rev ${s.revision}` : ""} · ${s.document_type}`],
    ["Department", s.department],
    ["Filled in by", `${s.filled_by?.name ?? "—"}, ${formatDateTime(s.filled_on)}`],
    ["Filed by", `${s.filed_by?.name ?? "—"}, ${formatDateTime(s.filed_on)}`],
    ["Completed", `${s.completed_items}/${s.total_items} (${s.completion_percent}%)`],
  ];

  return (
    <Box className="approval-review-page" sx={approvalReviewStyles}>
      <PageHeader title={`${s.name} · ${summary.record_number}`} subtitle="Filed quality record" onBack={onBack} />
      <div className="review-content">
        <div className="review-col">
          <InfoCard title="Record Summary">
            {rows.map(([label, value]) => (
              <div className="summary-row" key={label}>
                <span className="summary-label">{label}</span>
                <span className="summary-value">{value}</span>
              </div>
            ))}
          </InfoCard>
          <InfoCard title="Readings" flush>
            <ReadingsTable readings={s.fields} />
          </InfoCard>
          <InfoCard title="Document" flush>
            <div className="doc-head">
              <div className="doc-title">
                <span>{summary.document?.filename ?? "No document"}</span>
              </div>
              {summary.document && (
                <div style={{ display: "flex", gap: 8 }}>
                  <Button
                    className="open-btn"
                    startIcon={<OpenInNewIcon fontSize="small" />}
                    onClick={() =>
                      openAuthedFile(timeline?.workflow ? `api/signatures/${timeline.workflow.id}/preview` : summary.document!.file_url)
                    }
                  >
                    Open
                  </Button>
                  <Button
                    className="open-btn"
                    startIcon={<DownloadOutlinedIcon fontSize="small" />}
                    // the filed record as signed - the same document Open shows - not the bare scan
                    onClick={() =>
                      downloadAuthedFile(
                        timeline?.workflow ? `api/signatures/${timeline.workflow.id}/preview` : summary.document!.download_url,
                        `${summary.record_number}${timeline?.workflow ? "-signed" : ""}.pdf`,
                      )
                    }
                  >
                    Download
                  </Button>
                </div>
              )}
            </div>
            <div className="doc-preview">
              {preview.loading ? <PageLoader /> : preview.url ? <iframe title="Filed record" src={preview.url} /> : <ErrorState message={preview.error ?? "No preview."} />}
            </div>
          </InfoCard>
        </div>
        <div className="review-col">
          <InfoCard title="Approval Timeline" flush>
            {timeline ? <ApprovalTimeline steps={toTimeline(timeline)} /> : <PageLoader />}
          </InfoCard>
          {timeline && timeline.events.length > 0 && (
            <InfoCard title="Trail">
              {timeline.events.map((e) => (
                <div className="summary-row" key={e.id}>
                  <span className="summary-label">{formatDateTime(e.at)}</span>
                  <span className="summary-value">{e.summary}</span>
                </div>
              ))}
            </InfoCard>
          )}
        </div>
      </div>
    </Box>
  );
};

export default RecordFileDetail;
