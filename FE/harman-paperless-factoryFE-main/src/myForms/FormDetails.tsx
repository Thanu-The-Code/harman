import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Box, Button, IconButton, Tab, Tabs } from "@mui/material";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import { formDetailStyles } from "./style";
import { recordFillStyles } from "./recordStyles";
import CollapsibleCard from "./CollapsibleCard";
import RecordEvidence from "./RecordEvidence";
import TrackStatus from "./TrackStatus";
import { LayoutRecordForm, ValuesForm } from "./RecordForm";
import { currentRemark, currentValue, type Edits } from "./recordValue";
import RagDot from "../base/status/RagDot";
import RaiseRcrDialog from "../changeRequest/RaiseRcrDialog";
import { ErrorState, PageLoader } from "../base/feedback";
import { retryUnlessFinal } from "../base/feedback/retry";
import { useGetRecordQuery, useSaveValuesMutation, type RecordDetail } from "../api/records.api";
import { getApiErrorMessage } from "../api/errors";
import { formatDateTime } from "../utils/date";

const AUTOSAVE_MS = 1200;

/** Can readings be changed right now? Filling, or correcting during a CFT re-verification. */
const isEditable = (r: RecordDetail) =>
  r.stage === "filling" ? r.can.fill : r.stage === "cft_review" && r.reverify_count > 0 && r.can.amend;

const RecordEditor: React.FC<{ record: RecordDetail; tab: "record" | "track"; onTab: (t: "record" | "track") => void }> = ({
  record,
  tab,
  onTab,
}) => {
  const navigate = useNavigate();
  const [edits, setEdits] = useState<Edits>({});
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [rcrOpen, setRcrOpen] = useState(false);
  const [saveValues, { isLoading: saving }] = useSaveValuesMutation();

  const editable = isEditable(record);
  const byId = useMemo(() => new Map(record.values.map((v) => [v.id, v])), [record.values]);
  const dirty = Object.keys(edits).length > 0;
  const hasLayout = Array.isArray(record.format.layout) && record.format.layout.length > 0;

  const onChange = useCallback((id: string, patch: { value?: string; remark?: string }) => {
    setEdits((cur) => ({ ...cur, [id]: { ...cur[id], ...patch } }));
  }, []);

  /** Send these edits; drop the ones the server now holds (newer typing is kept). */
  const flush = useCallback(
    async (toSend: Edits): Promise<boolean> => {
      const entries = Object.entries(toSend);
      if (!entries.length) return true;
      const values = entries
        .map(([id]) => byId.get(id))
        .filter((v): v is NonNullable<typeof v> => !!v)
        .map((v) => ({ id: v.id, layout_key: v.layout_key, value: currentValue(v, toSend), remark: currentRemark(v, toSend) }));
      try {
        await saveValues({ id: record.id, values }).unwrap();
        setEdits((cur) => {
          const next = { ...cur };
          for (const [id, sent] of entries) {
            if (next[id]?.value === sent.value && next[id]?.remark === sent.remark) delete next[id];
          }
          return next;
        });
        setSaveError(null);
        setSavedAt(new Date().toISOString());
        return true;
      } catch (error) {
        // the edits stay pending on screen: say so, and how to try again
        setSaveError(`Not saved: ${getApiErrorMessage(error, "the server could not store them.")} Your entries are kept here; press Save to try again.`);
        return false;
      }
    },
    [byId, record.id, saveValues],
  );

  // auto-save a moment after the last keystroke
  useEffect(() => {
    if (!dirty || !editable) return;
    const timer = window.setTimeout(() => void flush(edits), AUTOSAVE_MS);
    return () => window.clearTimeout(timer);
  }, [edits, dirty, editable, flush]);

  const goSubmit = async () => {
    if (await flush(edits)) navigate(`/my-forms/${record.id}/approval`);
  };

  const filledCount = record.values.filter((v) => (currentValue(v, edits) || "").trim() !== "").length;

  return (
    <>
      <div className="detail-header">
        <IconButton className="back-btn" aria-label="Back" onClick={() => navigate("/my-forms")}>
          <ChevronLeftIcon />
        </IconButton>
        <div className="detail-heading">
          <h1 className="detail-title">{record.format.title}</h1>
          <div className="record-meta">
            <span>
              {record.number} · {record.format.code} rev {record.format_revision} · {record.period_label}
            </span>
            <RagDot rag={record.rag} label={record.rag_label} showLabel />
            <span className="stage-pill">{record.stage_label}</span>
            {record.stage !== "filling" && record.can.request_change && (
              <Button size="small" onClick={() => setRcrOpen(true)} sx={{ textTransform: "none", ml: "auto" }}>
                Request a change
              </Button>
            )}
          </div>
        </div>
      </div>
      {record.returned && (
        <div className="returned-note" role="alert">
          <strong>Returned for correction</strong> by {record.returned.by?.name ?? "an approver"},{" "}
          {formatDateTime(record.returned.at)}
          {record.returned.reason ? `: ${record.returned.reason}` : "."} Correct the record and submit it again.
        </div>
      )}
      {rcrOpen && <RaiseRcrDialog open record={record} onClose={() => setRcrOpen(false)} />}

      <Tabs className="detail-tabs" value={tab} onChange={(_, t) => onTab(t)} aria-label="Record sections">
        <Tab className="detail-tab" value="record" label="Record" />
        <Tab className="detail-tab" value="track" label="Track status" />
      </Tabs>

      {tab === "track" ? (
        <div className="detail-panel">
          <TrackStatus record={record} />
        </div>
      ) : (
        <>
          <div className="detail-panel">
            {record.nok_open && (
              <div className="notice nok" role="alert">
                <span>
                  <strong>N-OK flagged</strong> to {record.nok_flagged_to?.name ?? "the Overall Process Owner"}: {record.nok_summary}
                </span>
              </div>
            )}
            {record.stage === "filling" && record.observation_status === "not_ok" && !record.nok_open && (
              <div className="notice warn">
                Some readings are outside specification. When submitted, the record is flagged to the Overall Process Owner.
              </div>
            )}
            {record.stage === "cft_review" && record.reverify_count > 0 && editable && (
              <div className="notice warn">
                Sent back for re-verification. Correcting a reading clears the CFT's earlier answers so they review it again.
              </div>
            )}
            {!editable && record.stage !== "filling" && (
              <div className="notice info">
                Submitted {formatDateTime(record.submitted_at)} — {record.stage_label}. Readings can no longer be changed here.
              </div>
            )}

            <div className="section-head">
              <h2 className="section-title">Reading</h2>
              <p className="section-caption">Each one is checked against its limits as you type.</p>
            </div>

            {(record.format.work_instruction || record.format.work_instruction_ref) && (
              <CollapsibleCard title="Work instruction" subtitle={record.format.work_instruction_ref ?? undefined} defaultOpen={editable}>
                <div className="work-instruction">{record.format.work_instruction ?? "See the referenced instruction."}</div>
              </CollapsibleCard>
            )}

            <RecordEvidence record={record} canEdit={editable} />

            <CollapsibleCard title={record.format.title} subtitle={`${record.format.code} · Rev ${record.format_revision}`}>
              {hasLayout ? (
                <LayoutRecordForm
                  layout={record.format.layout}
                  values={record.values}
                  edits={edits}
                  onChange={onChange}
                  readOnly={!editable}
                />
              ) : (
                <ValuesForm values={record.values} edits={edits} onChange={onChange} readOnly={!editable} />
              )}
            </CollapsibleCard>
          </div>

          <div className="detail-footer">
            <span className={`save-state ${saveError ? "error" : ""}`}>
              {saveError
                ? saveError
                : saving
                  ? "Saving…"
                  : dirty
                    ? "Unsaved changes"
                    : savedAt
                      ? `Saved ${formatDateTime(savedAt)}`
                      : `${filledCount} of ${record.values.length} entries filled`}
              {record.missing.length > 0 && !saveError && ` · ${record.missing.length} required still blank`}
            </span>
            <div className="footer-actions">
              {editable && (
                <Button className="no-approval-btn" disabled={!dirty || saving} onClick={() => void flush(edits)}>
                  Save
                </Button>
              )}
              {record.stage === "filling" && record.can.submit && (
                <Button className="approval-btn" variant="contained" disabled={saving} onClick={goSubmit}>
                  Set up Approval
                </Button>
              )}
            </div>
          </div>
        </>
      )}
    </>
  );
};

/** `/my-forms/:id` — fill a record, or follow it through approval (`?tab=track`). */
const FormDetailPage: React.FC = () => {
  const { id = "" } = useParams<{ id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get("tab") === "track" ? "track" : "record";
  const { data: record, isLoading, isError, error, refetch } = useGetRecordQuery(id);

  return (
    <Box className="form-detail-page" sx={formDetailStyles}>
      <Box sx={recordFillStyles}>
      {isLoading ? (
        <PageLoader label="Loading the record…" />
      ) : isError || !record ? (
        <ErrorState message={(error && "message" in error && error.message) || "Record not found."} onRetry={retryUnlessFinal(error, refetch)} />
      ) : (
        <RecordEditor
          key={record.id}
          record={record}
          tab={tab}
          onTab={(t) => setSearchParams(t === "track" ? { tab: "track" } : {}, { replace: true })}
        />
      )}
      </Box>
    </Box>
  );
};

export default FormDetailPage;
