import React, { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Autocomplete, Box, Button, IconButton, MenuItem, TextField } from "@mui/material";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import TaskAltOutlinedIcon from "@mui/icons-material/TaskAltOutlined";
import { toast } from "react-toastify";
import { approvalStyles } from "./style";
import { ApprovalStartedDialog } from "./ApprovalDialogs";
import { ErrorState, PageLoader } from "../base/feedback";
import { retryUnlessFinal } from "../base/feedback/retry";
import { useFormatPeopleQuery, type PersonRef } from "../api/formats.api";
import {
  useGetRecordQuery,
  useSubmitRecordMutation,
  type RecordDetail,
  type RecordRouteStep,
  type ResponsibilityRole,
} from "../api/records.api";
import { getApiErrorMessage } from "../api/errors";

/** The roles a submitter may choose people for (the overrides the API accepts). */
const CHOOSABLE = ["process_owner", "overall_process_owner", "cft_members"] as const;
type Choosable = (typeof CHOOSABLE)[number];

const ROLE_LABEL: Record<Choosable, string> = {
  process_owner: "Process Owner",
  overall_process_owner: "Overall Process Owner",
  cft_members: "Quality CFT members",
};

const isChoosable = (role: string): role is Choosable => (CHOOSABLE as readonly string[]).includes(role);

const personLabel = (p: PersonRef) => (p.job_title ? `${p.name} — ${p.job_title}` : p.name);

/** Pre-selection: what the record already carries, else the people the format names. */
const initialChoice = (record: RecordDetail): Record<Choosable, string[]> => {
  const fromRoute = (role: Choosable) => record.route.find((s) => s.addressed_to === role)?.people.map((p) => p.id) ?? [];
  return {
    process_owner: record.approval_overrides.process_owner ?? fromRoute("process_owner"),
    overall_process_owner: record.approval_overrides.overall_process_owner ?? fromRoute("overall_process_owner"),
    cft_members: record.approval_overrides.cft_members ?? fromRoute("cft_members"),
  };
};

const stepFacts = (s: RecordRouteStep) =>
  [s.requires_signature ? "signed" : "no signature", s.mode === "all" ? "every member answers" : "any one approves", `${s.days} day${s.days === 1 ? "" : "s"}`].join(" · ");

const ApprovalSetup: React.FC<{ record: RecordDetail; onStarted: () => void }> = ({ record, onStarted }) => {
  const navigate = useNavigate();
  const { data: people, isLoading: loadingPeople } = useFormatPeopleQuery(record.format.id);
  const [submit, { isLoading: submitting }] = useSubmitRecordMutation();
  const [choice, setChoice] = useState<Record<Choosable, string[]>>(() => initialChoice(record));

  const options = (role: Choosable): PersonRef[] => people?.[role] ?? [];
  const nameOf = useMemo(() => {
    const all = new Map<string, string>();
    CHOOSABLE.forEach((role) => (people?.[role] ?? []).forEach((p) => all.set(p.id, p.name)));
    record.route.forEach((s) => s.people.forEach((p) => all.set(p.id, p.name)));
    return (id: string) => all.get(id) ?? "Unknown";
  }, [people, record.route]);

  const rolesInRoute = CHOOSABLE.filter((role) => record.route.some((s) => s.addressed_to === role));
  const missing = rolesInRoute.filter((role) => choice[role].length === 0);

  const handleStart = async () => {
    if (missing.length) {
      toast.error(`Choose the ${missing.map((r) => ROLE_LABEL[r]).join(", ")}.`);
      return;
    }
    const approval_overrides = Object.fromEntries(rolesInRoute.map((role) => [role, choice[role]])) as Partial<
      Record<ResponsibilityRole, string[]>
    >;
    try {
      await submit({ id: record.id, approval_overrides }).unwrap();
      onStarted();
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Could not start the approval."));
    }
  };

  const seen = new Set<string>();

  return (
    <>
      <div className="approval-body">
        <div className="approval-section-head">
          <div>
            <h2 className="approval-section-title">1. Confirm who approves</h2>
            <p className="approval-caption">
              The record follows the process route, top to bottom. People named on the format are pre-selected; a role the
              format leaves open must be chosen here.
            </p>
          </div>
          <div className="approval-section-actions">
            <span className="step-count">
              {record.route.length} {record.route.length === 1 ? "step" : "steps"}
            </span>
          </div>
        </div>

        {record.route.map((step) => {
          const role = step.addressed_to;
          const repeat = seen.has(role);
          seen.add(role);
          return (
            <div className="step-card" key={step.order}>
              <div className="step-top">
                <span className="step-badge">Step {step.order}</span>
                <strong style={{ flex: 1 }}>{step.name}</strong>
                <span className="step-count">{stepFacts(step)}</span>
              </div>
              <div className="step-fields" style={{ gridTemplateColumns: "1fr" }}>
                {!isChoosable(role) ? (
                  <div>
                    <div className="field-label">Who</div>
                    <span>{step.people.map((p) => p.name).join(", ") || "Named on the format"}</span>
                  </div>
                ) : repeat ? (
                  <div>
                    <div className="field-label">{ROLE_LABEL[role]}</div>
                    <span>Same as above: {choice[role].map(nameOf).join(", ") || "—"}</span>
                  </div>
                ) : role === "cft_members" ? (
                  <div>
                    <div className="field-label">{ROLE_LABEL[role]}</div>
                    <Autocomplete
                      multiple
                      size="small"
                      loading={loadingPeople}
                      options={options(role)}
                      value={options(role).filter((p) => choice[role].includes(p.id))}
                      getOptionLabel={personLabel}
                      isOptionEqualToValue={(a, b) => a.id === b.id}
                      onChange={(_, chosen) => setChoice((c) => ({ ...c, [role]: chosen.map((p) => p.id) }))}
                      renderInput={(params) => (
                        <TextField {...params} placeholder="Every member must answer" error={choice[role].length === 0} />
                      )}
                    />
                  </div>
                ) : (
                  <div>
                    <div className="field-label">{ROLE_LABEL[role]}</div>
                    <TextField
                      select
                      size="small"
                      fullWidth
                      className="step-select"
                      value={options(role).some((p) => p.id === choice[role][0]) ? choice[role][0] : ""}
                      onChange={(e) => setChoice((c) => ({ ...c, [role]: e.target.value ? [e.target.value] : [] }))}
                      error={choice[role].length === 0}
                    >
                      <MenuItem value="">
                        <em>Choose</em>
                      </MenuItem>
                      {options(role).map((p) => (
                        <MenuItem key={p.id} value={p.id}>
                          {personLabel(p)}
                        </MenuItem>
                      ))}
                    </TextField>
                  </div>
                )}
              </div>
            </div>
          );
        })}

        <h2 className="approval-section-title review-title">2. Review and confirm the approval route</h2>
        <div className="review-card">
          <div className="review-head">
            <span className="review-icon">
              <TaskAltOutlinedIcon fontSize="small" />
            </span>
            <span className="review-heading">What will happen to this record</span>
          </div>
          {record.route.map((s) => (
            <div className="review-step" key={s.order}>
              <span className="review-step-badge">Step {s.order}</span>
              <span>
                {s.name}:{" "}
                <strong>
                  {isChoosable(s.addressed_to)
                    ? choice[s.addressed_to].map(nameOf).join(", ") || "not chosen yet"
                    : s.people.map((p) => p.name).join(", ")}
                </strong>
              </span>
            </div>
          ))}
          {record.missing.length > 0 && (
            <div className="review-priority review-warning" role="alert">
              <strong>
                {record.missing.length} required {record.missing.length === 1 ? "entry is" : "entries are"} still blank:
              </strong>{" "}
              {record.missing.slice(0, 6).join("; ")}
              {record.missing.length > 6 ? ` and ${record.missing.length - 6} more` : ""}. You can still submit; the
              approvers are shown what is blank.
            </div>
          )}
          <div className="review-priority">
            {record.observation_status === "not_ok"
              ? "Some readings are N-OK: the record goes as high priority and is flagged to the Overall Process Owner."
              : "All readings so far are within specification."}{" "}
            Once approved, it is filed in <strong>{record.storage_preview}</strong>.
          </div>
        </div>
      </div>

      <div className="approval-footer">
        <Button className="skip-btn" onClick={() => navigate(`/my-forms/${record.id}`)}>
          Back to the record
        </Button>
        <Button className="start-btn" variant="contained" disabled={submitting || missing.length > 0} onClick={handleStart}>
          {submitting ? "Starting…" : "Start Approval"}
        </Button>
      </div>
    </>
  );
};

/** `/my-forms/:id/approval` — submit a filled record into its approval chain. */
const ApprovalSetupPage: React.FC = () => {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: record, isLoading, isError, error, refetch } = useGetRecordQuery(id);
  // set on success: the refetched record is no longer "filling", and the page must stay put for the dialog
  const [started, setStarted] = useState(false);
  const goToDocuments = () => navigate("/my-forms");

  return (
    <Box className="approval-page" sx={approvalStyles}>
      <div className="approval-header">
        <IconButton className="back-btn" aria-label="Back" onClick={() => navigate(`/my-forms/${id}`)}>
          <ChevronLeftIcon />
        </IconButton>
        <h1 className="approval-title">Set up approval{record ? ` · ${record.number}` : ""}</h1>
      </div>
      {isLoading ? (
        <PageLoader />
      ) : isError || !record ? (
        <ErrorState message={(error && "message" in error && error.message) || "Record not found."} onRetry={retryUnlessFinal(error, refetch)} />
      ) : record.stage !== "filling" && !started ? (
        <ErrorState message={`This record is already ${record.stage_label.toLowerCase()}.`} />
      ) : (
        <ApprovalSetup key={record.id} record={record} onStarted={() => setStarted(true)} />
      )}
      <ApprovalStartedDialog open={started} onViewDocuments={goToDocuments} onDone={goToDocuments} />
    </Box>
  );
};

export default ApprovalSetupPage;
