import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Box, Button, IconButton } from "@mui/material";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import CloseIcon from "@mui/icons-material/Close";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import AccessTimeOutlinedIcon from "@mui/icons-material/AccessTimeOutlined";
import InfoCard from "../base/info";
import { PageLoader } from "../base/feedback";
import RaiseDcrDialog from "../changeRequest/RaiseDcrDialog";
import { templateDetailStyles } from "./style";
import { formatStatusLabel, useGetFormatQuery, type RepositoryTemplate } from "../api/formats.api";
import { useAuthedObjectUrl } from "../hooks/useAuthedObjectUrl";
import { formatDate, formatDateTime } from "../utils/date";

/** One template with its revision history (Template Repository). */
const TemplateDetail = ({ template, onBack }: { template: RepositoryTemplate; onBack: () => void }) => {
  const navigate = useNavigate();
  const [showHistory, setShowHistory] = useState(true);
  const [dcrOpen, setDcrOpen] = useState(false);
  const latestId = template.latest_version.id;
  const { data: format, isLoading } = useGetFormatQuery(latestId);
  const blank = useAuthedObjectUrl(format?.has_blank ? `api/formats/${latestId}/blank?inline=true` : null);
  const released = template.released_version;

  const leftSummary: [string, string][] = [
    ["Code", template.code],
    ["Team", template.team?.name ?? "—"],
    ["Frequency", template.frequency_label],
    ["Released", released ? `Rev ${released.revision}, ${formatDate(released.effective_date)}` : "Not released"],
    ["Revisions", String(template.version_count)],
  ];
  const rightSummary: [string, string][] = [
    ["Process Owner", format?.process_owner?.name ?? "Chosen at submission"],
    ["Overall P. Owner", format?.overall_process_owner?.name ?? "Chosen at submission"],
    ["QMS Coordinator", format?.qms_coordinator?.name ?? "—"],
    ["Recorded entries", String(format?.field_count ?? "—")],
    ["Filed in", format?.storage_preview ?? "—"],
  ];

  return (
    <Box className="template-detail-page" sx={templateDetailStyles}>
      <header className="template-detail-header">
        <IconButton aria-label="Back to templates" onClick={onBack}>
          <ChevronLeftIcon />
        </IconButton>
        <h1>
          {template.code} · {template.title}
        </h1>
      </header>

      <main className={`template-detail-content${showHistory ? "" : " history-hidden"}`}>
        <section className="template-document-column">
          <InfoCard title="Template Summary">
            <div className="summary-grid">
              {[leftSummary, rightSummary].map((column, index) => (
                <div className="summary-column" key={index}>
                  {column.map(([label, value]) => (
                    <div className="summary-row" key={label}>
                      <span className="summary-label">{label}</span>
                      <span className="summary-value">{value}</span>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </InfoCard>

          <InfoCard title="" flush className="document-preview-card">
            <div className="doc-head">
              <div className="doc-title">
                <span>
                  Rev {template.latest_version.revision} ·{" "}
                  {formatStatusLabel(template.latest_version.status, template.latest_version.approval_status)}
                </span>
              </div>
              <Button className="open-document-btn" startIcon={<OpenInNewIcon />} onClick={() => navigate(`/builder/${latestId}`)}>
                Open template
              </Button>
            </div>

            <div className="doc-meta">
              <span>{format?.has_blank ? "Blank form attached" : "Filled on screen (no blank attached)"}</span>
              <span>Created {formatDateTime(template.latest_version.created_at)}</span>
            </div>

            <div className="doc-preview">
              {isLoading || blank.loading ? (
                <PageLoader />
              ) : blank.url ? (
                <iframe title={`${template.title} blank form`} src={blank.url} />
              ) : (
                <div className="doc-page">
                  <div className="doc-brand">
                    <span className="doc-brand-logo" />
                    <span>
                      Paperless Factory<small>A Harman Product</small>
                    </span>
                  </div>
                  <h2>{template.title}</h2>
                  {(format?.fields ?? []).slice(0, 12).map((f) => (
                    <div key={f.id} style={{ display: "flex", justifyContent: "space-between", fontSize: 12, padding: "4px 0" }}>
                      <span>{f.label}</span>
                      <span style={{ color: "#0f766e" }}>{f.spec_label}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </InfoCard>
        </section>

        {showHistory && (
          <section className="version-history-panel">
            <div className="version-history-header">
              <div>
                <h2>Version History</h2>
                <p>Every revision of this template, newest first.</p>
              </div>
              <IconButton aria-label="Close version history" onClick={() => setShowHistory(false)}>
                <CloseIcon fontSize="small" />
              </IconButton>
            </div>
            <div className="version-history-list">
              {/* by revision, not the order the list arrived in: "01" above "00" */}
              {[...template.versions]
                .sort((a, b) => String(b.revision).localeCompare(String(a.revision), undefined, { numeric: true }))
                .map((version) => (
                <article className="version-item" key={version.id}>
                  <span className="version-marker" />
                  <div className="version-card">
                    <div className="version-heading">
                      <strong>Rev {version.revision}</strong>
                      <IconButton aria-label={`View rev ${version.revision}`} onClick={() => navigate(`/builder/${version.id}`)}>
                        <VisibilityOutlinedIcon />
                      </IconButton>
                    </div>
                    <div className="version-date">
                      <AccessTimeOutlinedIcon />
                      <span>{formatDateTime(version.effective_date ?? version.created_at)}</span>
                    </div>
                    <ul>
                      <li>{formatStatusLabel(version.status, version.approval_status)}</li>
                      {version.title !== template.title && <li>Titled “{version.title}”</li>}
                    </ul>
                  </div>
                </article>
              ))}
            </div>
          </section>
        )}
      </main>

      <footer className="template-detail-actions">
        <Button className="create-version-btn" disabled={!released} onClick={() => setDcrOpen(true)}>
          Create New Version
        </Button>
        <Button className="use-template-btn" variant="contained" onClick={() => navigate(`/builder/${latestId}`)}>
          Open template
        </Button>
      </footer>

      {released && dcrOpen && (
        <RaiseDcrDialog
          open
          format={{ id: released.id, code: template.code, title: template.title }}
          onClose={() => setDcrOpen(false)}
        />
      )}
    </Box>
  );
};

export default TemplateDetail;
