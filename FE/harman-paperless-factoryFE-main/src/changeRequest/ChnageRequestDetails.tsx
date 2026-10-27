import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Box, Button, MenuItem, TextField } from "@mui/material";
import { toast } from "react-toastify";
import { changeDetailStyles } from "./style";
import PageHeader from "../base/pageHeader";
import InfoCard from "../base/info";
import KeyValueGrid, { type KeyValue } from "../base/keyValue/KeyValueGrid";
import CustomChip from "../base/chip/CustomChip";
import CustomDialog from "../base/dialog/CustomDialog";
import CustomTextField from "../base/dialog/CustomTextField";
import CustomTextArea from "../base/dialog/CustomTextarea";
import { ErrorState, PageLoader } from "../base/feedback";
import { retryUnlessFinal } from "../base/feedback/retry";
import { DecisionDialog } from "../myApprovals/ActionDialogs";
import { useMeQuery } from "../api/auth.api";
import {
  useAssignRcrMutation,
  useDecideDcrMutation,
  useDecideRcrMutation,
  useExecuteDcrMutation,
  useGetDcrQuery,
  useGetRcrQuery,
  useImplementRcrMutation,
  useReviewDcrMutation,
  useUpdateRcrMutation,
  type Dcr,
  type Rcr,
} from "../api/changeRequests.api";
import { FREQUENCY_OPTIONS, useFormatApproversQuery, type Frequency } from "../api/formats.api";
import { getApiErrorMessage } from "../api/errors";
import { openAuthedFile } from "../utils/openAuthedFile";
import { formatDateTime } from "../utils/date";

const chip = (status: string): "green" | "orange" | "blue" | "purple" =>
  ["approved", "implemented"].includes(status) ? "green" : ["rejected", "not_approved"].includes(status) ? "orange" : status === "under_review" ? "purple" : "blue";

const run = async (action: () => Promise<unknown>, success: string, failure: string) => {
  try {
    await action();
    toast.success(success);
    return true;
  } catch (error) {
    toast.error(getApiErrorMessage(error, failure));
    return false;
  }
};

/* ------------------------------------------------------------------- DCR */

const DcrDetail = ({ dcr }: { dcr: Dcr }) => {
  const navigate = useNavigate();
  const { data: me } = useMeQuery();
  const [review, { isLoading: reviewing }] = useReviewDcrMutation();
  const [decide, { isLoading: deciding }] = useDecideDcrMutation();
  const [execute, { isLoading: executing }] = useExecuteDcrMutation();
  const [dialog, setDialog] = useState<"approve" | "reject" | "execute" | null>(null);
  const [code, setCode] = useState("");
  const [title, setTitle] = useState(dcr.title);
  const [frequency, setFrequency] = useState<Frequency>("daily");

  const left: KeyValue[] = [
    ["Request", `${dcr.number} · ${dcr.kind_label}`],
    ["Format", dcr.format ? `${dcr.format.code} rev ${dcr.format.revision} · ${dcr.format.title}` : "A new format"],
    ["Team", dcr.team?.name ?? "—"],
    ["Raised by", `${dcr.raised_by?.name ?? "—"}, ${formatDateTime(dcr.raised_at)}`],
  ];
  const right: KeyValue[] = [
    ["QMS Coordinator", dcr.coordinator?.name ?? "—"],
    ["Status", dcr.status_label],
    ["Decided", dcr.decided_at ? `${dcr.decided_by?.name ?? ""}, ${formatDateTime(dcr.decided_at)}` : "—"],
    ["Result", dcr.resulting_format ? `${dcr.resulting_format.code} rev ${dcr.resulting_format.revision} (${dcr.resulting_format.status})` : "—"],
  ];

  const isNew = dcr.kind === "new_format";
  const canDecide = dcr.can.decide && ["submitted", "under_review"].includes(dcr.status);

  return (
    <>
      <PageHeader title={dcr.title} subtitle={`${dcr.number} · ${dcr.kind_label}`} onBack={() => navigate("/request")} />
      <div className="detail-content">
        <InfoCard title="Request Detail">
          <KeyValueGrid columns={[left, right]} />
        </InfoCard>

        <InfoCard title="Change Request Details" flush>
          <div className="cr-body">
            <div className="cr-label">Why the change is needed</div>
            <div className="cr-reason">{dcr.reason}</div>
            {dcr.current_state && (
              <>
                <div className="cr-label">What it says now</div>
                <div className="cr-reason">{dcr.current_state}</div>
              </>
            )}
            <div className="cr-label">{isNew ? "What the new format must record" : "Proposed change"}</div>
            <div className="cr-reason">{dcr.proposed_change}</div>
            {dcr.justification && (
              <>
                <div className="cr-label">Justification</div>
                <div className="cr-reason">{dcr.justification}</div>
              </>
            )}
            {dcr.decision_comment && (
              <>
                <div className="cr-label">Coordinator's comment</div>
                <div className="cr-reason">{dcr.decision_comment}</div>
              </>
            )}
          </div>

          <div className="cr-footer">
            {canDecide ? (
              <>
                {dcr.status === "submitted" && (
                  <Button className="decision-btn" disabled={reviewing} onClick={() => run(() => review(dcr.id).unwrap(), "Marked as under review.", "Could not start the review.")}>
                    Start review
                  </Button>
                )}
                <Button className="decision-btn not-approved-btn" onClick={() => setDialog("reject")}>
                  Not Approved
                </Button>
                <Button className="decision-btn approved-btn" variant="contained" onClick={() => setDialog("approve")}>
                  Approved
                </Button>
              </>
            ) : (
              <CustomChip label={dcr.status_label} variant={chip(dcr.status)} />
            )}
          </div>
        </InfoCard>
      </div>

      <div className="bottom-bar">
        {dcr.can.execute && dcr.status === "approved" && (
          <Button className="bar-btn assign-btn" onClick={() => setDialog("execute")}>
            {isNew ? "Create the new format" : "Create the new revision"}
          </Button>
        )}
        {dcr.resulting_format && me?.is_admin && (
          <Button
            className="bar-btn"
            onClick={() => navigate(`/builder/${dcr.resulting_format!.id}/build?format_id=${dcr.resulting_format!.id}`)}
          >
            Open the draft in the designer
          </Button>
        )}
      </div>

      {dialog === "approve" && (
        <DecisionDialog
          open
          onClose={() => setDialog(null)}
          title="Approve the change request"
          subtitle="It can then be executed: the new revision (or new format) is created as a draft."
          confirmText="Approve"
          noteLabel="Comment"
          busy={deciding}
          onConfirm={async ({ note }) => {
            if (await run(() => decide({ id: dcr.id, action: "approve", comment: note }).unwrap(), "Approved. The raiser and Process Owner are notified.", "Could not approve."))
              setDialog(null);
          }}
        />
      )}
      {dialog === "reject" && (
        <DecisionDialog
          open
          onClose={() => setDialog(null)}
          title="Not approved"
          subtitle="The raiser and the Process Owner are told, with your comment."
          confirmText="Not approved"
          noteLabel="Why is it not approved?"
          noteRequired
          busy={deciding}
          onConfirm={async ({ note }) => {
            if (await run(() => decide({ id: dcr.id, action: "reject", comment: note }).unwrap(), "Marked as not approved.", "Could not record the decision."))
              setDialog(null);
          }}
        />
      )}
      <CustomDialog
        open={dialog === "execute"}
        onClose={() => setDialog(null)}
        title={isNew ? "Create the new format" : "Create the new revision"}
        subtitle={
          isNew
            ? "A draft format is created; it is released through the template review like any other."
            : `Rev ${dcr.format?.revision} is superseded by a new draft revision, released through the template review.`
        }
        confirmText={executing ? "Creating…" : "Create"}
        confirmDisabled={executing || (isNew && !title.trim())}
        onConfirm={async () => {
          const payload = isNew ? { code: code.trim().toUpperCase(), title: title.trim(), frequency } : {};
          try {
            const res = await execute({ id: dcr.id, ...payload }).unwrap();
            toast.success(`${res.format.code} rev ${res.format.revision} created as a draft.`);
            setDialog(null);
          } catch (error) {
            toast.error(getApiErrorMessage(error, "Could not execute the change request."));
          }
        }}
      >
        {isNew ? (
          <div style={{ display: "grid", gap: 12 }}>
            <CustomTextField label="Form code" value={code} onChange={setCode} placeholder="Leave blank for the team's next code" />
            <CustomTextField label="Form title" value={title} onChange={setTitle} />
            <TextField select size="small" label="Frequency" value={frequency} onChange={(e) => setFrequency(e.target.value as Frequency)}>
              {FREQUENCY_OPTIONS.map((f) => (
                <MenuItem key={f.value} value={f.value}>
                  {f.label}
                </MenuItem>
              ))}
            </TextField>
          </div>
        ) : (
          <span>The approved change is then made in the designer and the revision sent for approval.</span>
        )}
      </CustomDialog>
    </>
  );
};

/* ------------------------------------------------------------------- RCR */

const RcrDetail = ({ rcr }: { rcr: Rcr }) => {
  const navigate = useNavigate();
  const { data: approvers = [] } = useFormatApproversQuery(undefined, { skip: !rcr.can.assign });
  const [update, { isLoading: updating }] = useUpdateRcrMutation();
  const [assign, { isLoading: assigning }] = useAssignRcrMutation();
  const [decide, { isLoading: deciding }] = useDecideRcrMutation();
  const [implement, { isLoading: implementing }] = useImplementRcrMutation();
  const [dialog, setDialog] = useState<"edit" | "assign" | "approve" | "reject" | "implement" | null>(null);
  const [title, setTitle] = useState(rcr.title);
  const [reason, setReason] = useState(rcr.reason);
  const [assignee, setAssignee] = useState(rcr.assigned_to?.id ?? "");
  const rec = rcr.record;

  const left: KeyValue[] = [
    ["Record", rec ? `${rec.number}` : "—"],
    ["Document", rec ? `${rec.document_name}${rec.format ? ` (${rec.format.code} rev ${rec.format.revision})` : ""}` : "—"],
    ["Department", rec?.department ?? "—"],
    ["Filled by", rec ? `${rec.filled_by?.name ?? "—"}, ${formatDateTime(rec.filled_at)}` : "—"],
    ["Completed", rec ? `${rec.completed_items}/${rec.total_items} (${rec.completion_percent}%)` : "—"],
  ];
  const right: KeyValue[] = [
    ["Raised by", `${rcr.raised_by?.name ?? "—"}, ${formatDateTime(rcr.raised_at)}`],
    ["Assigned to", rcr.assigned_to?.name ?? "—"],
    ["Status", rcr.status_label],
    ["Decided", rcr.decided_at ? `${rcr.decided_by?.name ?? ""}, ${formatDateTime(rcr.decided_at)}` : "—"],
    ["Implemented", rcr.implemented_at ? `${rcr.implemented_by?.name ?? ""}, ${formatDateTime(rcr.implemented_at)}` : "—"],
  ];

  const close = () => setDialog(null);

  return (
    <>
      <PageHeader title={rcr.title} subtitle={`${rcr.number} · record change request`} onBack={() => navigate("/request?type=rcr")} />
      <div className="detail-content">
        <InfoCard title="Record Detail">
          <KeyValueGrid columns={[left, right]} />
          {rec?.document && (
            <Button size="small" sx={{ mt: 1, textTransform: "none" }} onClick={() => openAuthedFile(rec.document!.file_url)}>
              Open the record's document
            </Button>
          )}
        </InfoCard>

        <InfoCard title="Change Request Details" flush>
          <div className="cr-body">
            <div className="cr-label">Why the record needs to change</div>
            <div className="cr-reason">{rcr.reason}</div>
            {rcr.decision_comment && (
              <>
                <div className="cr-label">Decision comment</div>
                <div className="cr-reason">{rcr.decision_comment}</div>
              </>
            )}
            {rcr.implementation_note && (
              <>
                <div className="cr-label">What was done</div>
                <div className="cr-reason">{rcr.implementation_note}</div>
              </>
            )}
          </div>
          <div className="cr-footer">
            {rcr.can.decide && rcr.status === "open" ? (
              <>
                <Button className="decision-btn not-approved-btn" onClick={() => setDialog("reject")}>
                  Not Approved
                </Button>
                <Button className="decision-btn approved-btn" variant="contained" onClick={() => setDialog("approve")}>
                  Approved
                </Button>
              </>
            ) : (
              <CustomChip label={rcr.status_label} variant={chip(rcr.status)} />
            )}
          </div>
        </InfoCard>
      </div>

      <div className="bottom-bar">
        <Button className="bar-btn" disabled={!rcr.can.edit} onClick={() => setDialog("edit")}>
          Edit
        </Button>
        <Button className="bar-btn" disabled={!rcr.can.assign} onClick={() => setDialog("assign")}>
          Assign
        </Button>
        {rcr.can.implement && (
          <Button className="bar-btn assign-btn" onClick={() => setDialog("implement")}>
            Mark implemented
          </Button>
        )}
      </div>

      <CustomDialog
        open={dialog === "edit"}
        onClose={close}
        title="Edit the request"
        confirmText={updating ? "Saving…" : "Save"}
        confirmDisabled={updating || !title.trim() || !reason.trim()}
        onConfirm={async () => {
          if (await run(() => update({ id: rcr.id, title: title.trim(), reason: reason.trim() }).unwrap(), "Saved.", "Could not save.")) close();
        }}
      >
        <CustomTextField label="Title" value={title} onChange={setTitle} />
        <CustomTextArea label="Why the record needs to change" value={reason} onChange={setReason} rows={4} />
      </CustomDialog>
      <CustomDialog
        open={dialog === "assign"}
        onClose={close}
        title="Assign the request"
        confirmText={assigning ? "Assigning…" : "Assign"}
        confirmDisabled={assigning || !assignee}
        onConfirm={async () => {
          if (await run(() => assign({ id: rcr.id, assigned_to_id: assignee }).unwrap(), "Assigned.", "Could not assign.")) close();
        }}
      >
        <TextField select fullWidth size="small" label="Decided by" value={assignee} onChange={(e) => setAssignee(e.target.value)}>
          {approvers.map((p) => (
            <MenuItem key={p.id} value={p.id}>
              {p.name}
              {p.job_title ? ` — ${p.job_title}` : ""}
            </MenuItem>
          ))}
        </TextField>
      </CustomDialog>
      {dialog === "approve" && (
        <DecisionDialog
          open
          onClose={close}
          title="Approve the record change"
          confirmText="Approve"
          noteLabel="Comment"
          busy={deciding}
          onConfirm={async ({ note }) => {
            if (await run(() => decide({ id: rcr.id, action: "approve", comment: note }).unwrap(), "Approved.", "Could not approve.")) close();
          }}
        />
      )}
      {dialog === "reject" && (
        <DecisionDialog
          open
          onClose={close}
          title="Not approved"
          confirmText="Not approved"
          noteLabel="Why is it not approved?"
          noteRequired
          busy={deciding}
          onConfirm={async ({ note }) => {
            if (await run(() => decide({ id: rcr.id, action: "not_approved", comment: note }).unwrap(), "Marked as not approved.", "Could not record the decision."))
              close();
          }}
        />
      )}
      {dialog === "implement" && (
        <DecisionDialog
          open
          onClose={close}
          title="Mark as implemented"
          subtitle="Say what was changed and where, so the record's trail shows it."
          confirmText="Implemented"
          noteLabel="What was done"
          noteRequired
          busy={implementing}
          onConfirm={async ({ note }) => {
            if (await run(() => implement({ id: rcr.id, note }).unwrap(), "Marked as implemented.", "Could not record it.")) close();
          }}
        />
      )}
    </>
  );
};

/** `/change-request/:kind/:id` — kind is "dcr" (format) or "rcr" (record). */
const ChangeRequestDetailPage = () => {
  const { kind = "dcr", id = "" } = useParams<{ kind?: string; id: string }>();
  const isRcr = kind === "rcr";
  const dcr = useGetDcrQuery(id, { skip: isRcr });
  const rcr = useGetRcrQuery(id, { skip: !isRcr });
  const q = isRcr ? rcr : dcr;

  return (
    <Box className="change-detail-page" sx={changeDetailStyles}>
      {q.isLoading ? (
        <PageLoader />
      ) : q.isError || !q.data ? (
        <ErrorState message="Change request not found." onRetry={retryUnlessFinal(q.error, q.refetch)} />
      ) : isRcr ? (
        <RcrDetail key={id} rcr={rcr.data!} />
      ) : (
        <DcrDetail key={id} dcr={dcr.data!} />
      )}
    </Box>
  );
};

export default ChangeRequestDetailPage;
