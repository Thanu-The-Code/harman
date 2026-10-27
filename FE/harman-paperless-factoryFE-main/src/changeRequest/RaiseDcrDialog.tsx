import { useState } from "react";
import { MenuItem, TextField } from "@mui/material";
import { toast } from "react-toastify";
import CustomDialog from "../base/dialog/CustomDialog";
import CustomTextField from "../base/dialog/CustomTextField";
import CustomTextArea from "../base/dialog/CustomTextarea";
import { useRaiseDcrMutation, type DcrKind } from "../api/changeRequests.api";
import { useFormatTeamsQuery, useListFormatsQuery, useResponsibilityPeopleQuery } from "../api/formats.api";
import { getApiErrorMessage } from "../api/errors";

interface Props {
  open: boolean;
  onClose: () => void;
  /** The released format to change; without it the person chooses (or asks for a new format). */
  format?: { id: string; code: string; title: string };
}

/**
 * "Any change in existing format / generation of new format": a Document
 * Change Request goes to the QMS Coordinator, who approves it before anything
 * is altered.
 */
const RaiseDcrDialog = ({ open, onClose, format }: Props) => {
  const [raise, { isLoading }] = useRaiseDcrMutation();
  const { data: library } = useListFormatsQuery({ status: "active" }, { skip: !!format });
  const { data: teams } = useFormatTeamsQuery(undefined, { skip: !!format });
  // a new format has no QMS Coordinator to inherit: the raiser names one
  const { data: people } = useResponsibilityPeopleQuery(undefined, { skip: !!format });
  const [coordinatorId, setCoordinatorId] = useState("");
  const [kind, setKind] = useState<DcrKind>("change_existing");
  const [formatId, setFormatId] = useState(format?.id ?? "");
  const [teamId, setTeamId] = useState("");
  const [title, setTitle] = useState(format ? `Change to ${format.code}` : "");
  const [reason, setReason] = useState("");
  const [currentState, setCurrentState] = useState("");
  const [proposed, setProposed] = useState("");
  const [justification, setJustification] = useState("");

  const target = format ?? library?.formats.find((f) => f.id === formatId);
  const valid =
    title.trim() && reason.trim() && proposed.trim() &&
    (kind === "new_format" ? !!teamId && !!coordinatorId : !!(format?.id || formatId));

  const submit = async () => {
    try {
      const dcr = await raise({
        kind,
        ...(kind === "change_existing"
          ? { format_id: format?.id ?? formatId }
          : { team_id: teamId, qms_coordinator_id: coordinatorId }),
        title: title.trim(),
        reason: reason.trim(),
        current_state: currentState.trim() || undefined,
        proposed_change: proposed.trim(),
        justification: justification.trim() || undefined,
      }).unwrap();
      toast.success(`${dcr.number} raised and sent to ${dcr.coordinator?.name ?? "the QMS Coordinator"}.`);
      onClose();
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Could not raise the change request."));
    }
  };

  return (
    <CustomDialog
      open={open}
      onClose={onClose}
      onConfirm={submit}
      title="Raise a change request"
      subtitle={
        format ? (
          <>
            For <b>{format.code}</b> · {format.title}. The QMS Coordinator approves it before the format is changed.
          </>
        ) : (
          "The QMS Coordinator approves it before a format is changed or created."
        )
      }
      confirmText={isLoading ? "Sending…" : "Send to QMS Coordinator"}
      confirmDisabled={!valid || isLoading}
    >
      {!format && (
        <div style={{ display: "grid", gap: 12, marginBottom: 8 }}>
          <TextField select size="small" label="What is needed" value={kind} onChange={(e) => setKind(e.target.value as DcrKind)}>
            <MenuItem value="change_existing">A change to a released format</MenuItem>
            <MenuItem value="new_format">A new format</MenuItem>
          </TextField>
          {kind === "change_existing" ? (
            <TextField
              select
              size="small"
              label="Format"
              value={formatId}
              onChange={(e) => {
                setFormatId(e.target.value);
                const f = library?.formats.find((x) => x.id === e.target.value);
                if (f && !title.trim()) setTitle(`Change to ${f.code}`);
              }}
            >
              {(library?.formats ?? []).map((f) => (
                <MenuItem key={f.id} value={f.id}>
                  {f.code} · {f.title} (rev {f.revision})
                </MenuItem>
              ))}
            </TextField>
          ) : (
            <>
              <TextField select size="small" label="Quality team" value={teamId} onChange={(e) => setTeamId(e.target.value)}>
                {(teams?.teams ?? [])
                  .filter((t) => t.is_active)
                  .map((t) => (
                    <MenuItem key={t.id} value={t.id}>
                      {t.code} - {t.name}
                    </MenuItem>
                  ))}
              </TextField>
              <TextField
                select
                size="small"
                label="QMS Coordinator"
                helperText="Who approves the new format"
                value={coordinatorId}
                onChange={(e) => setCoordinatorId(e.target.value)}
              >
                {(people?.qms_coordinator ?? []).map((p) => (
                  <MenuItem key={p.id} value={p.id}>
                    {p.name}
                    {p.job_title ? ` — ${p.job_title}` : ""}
                  </MenuItem>
                ))}
              </TextField>
            </>
          )}
        </div>
      )}
      <CustomTextField label="Title" value={title} onChange={setTitle} placeholder={target ? `Change to ${target.code}` : "New format for …"} />
      <CustomTextArea label="Why is a change needed?" value={reason} onChange={setReason} rows={3} />
      {kind === "change_existing" && (
        <CustomTextArea label="What it says now" optional value={currentState} onChange={setCurrentState} rows={2} />
      )}
      <CustomTextArea
        label={kind === "new_format" ? "What the new format must record" : "Proposed change"}
        value={proposed}
        onChange={setProposed}
        rows={3}
      />
      <CustomTextArea label="Justification / evidence" optional value={justification} onChange={setJustification} rows={2} />
    </CustomDialog>
  );
};

export default RaiseDcrDialog;
