import { useState } from "react";
import { Autocomplete, Box, Button, IconButton, MenuItem, TextField } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlinedIcon from "@mui/icons-material/DeleteOutlined";
import { toast } from "react-toastify";
import CustomDialog from "../../base/dialog/CustomDialog";
import {
  useFormatApproversQuery,
  useSubmitFormatApprovalMutation,
  type FormatDetail,
  type PersonRef,
  type ReviewStepPayload,
} from "../../api/formats.api";
import { getApiErrorMessage } from "../../api/errors";

type Priority = "low" | "normal" | "high" | "urgent";

const PRIORITIES: { value: Priority; label: string }[] = [
  { value: "low", label: "Low" },
  { value: "normal", label: "Normal" },
  { value: "high", label: "High" },
  { value: "urgent", label: "Urgent" },
];

const MAX_STEPS = 12;

interface Props {
  open: boolean;
  format: FormatDetail;
  onClose: () => void;
  onSubmitted: () => void;
}

/** The QMS Coordinator reviews a new template first, by default. */
const firstStep = (format: FormatDetail): ReviewStepPayload => ({
  name: "QMS Coordinator review",
  reviewer_ids: format.qms_coordinator ? [format.qms_coordinator.id] : [],
  mode: "any",
  due_days: 2,
});

/**
 * Template release review: ordered steps, each with its reviewers. The last
 * approval releases the template into the Resources library.
 */
const SubmitApprovalDialog = ({ open, format, onClose, onSubmitted }: Props) => {
  const { data: approvers = [] } = useFormatApproversQuery();
  const [submit, { isLoading }] = useSubmitFormatApprovalMutation();
  const [steps, setSteps] = useState<ReviewStepPayload[]>(() => [firstStep(format)]);
  const [priority, setPriority] = useState<Priority>("normal");

  const update = (index: number, patch: Partial<ReviewStepPayload>) =>
    setSteps((prev) => prev.map((s, i) => (i === index ? { ...s, ...patch } : s)));

  const valid = steps.length > 0 && steps.every((s) => s.name.trim() && s.reviewer_ids.length > 0);

  const handleSubmit = async () => {
    try {
      await submit({
        id: format.id,
        priority,
        steps: steps.map((s) => ({ ...s, name: s.name.trim(), due_days: s.due_days || null })),
      }).unwrap();
      toast.success("Sent for approval. The reviewers have been notified.");
      onSubmitted();
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Could not send the template for approval."));
    }
  };

  return (
    <CustomDialog
      open={open}
      onClose={onClose}
      onConfirm={handleSubmit}
      title="Send for approval"
      subtitle={
        <>
          {format.code} · {format.title}. Steps run top to bottom; the last approval releases the template.
        </>
      }
      confirmText={isLoading ? "Sending…" : "Send for approval"}
      confirmDisabled={!valid || isLoading}
      maxWidth="md"
    >
      <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
        {steps.map((step, index) => (
          <Box key={index} sx={{ border: "1px solid #e5e7eb", borderRadius: 2, p: 1.5 }}>
            <Box sx={{ display: "flex", gap: 1, alignItems: "center", mb: 1.5 }}>
              <Box component="span" sx={{ fontSize: 12, fontWeight: 600, color: "#0f766e", whiteSpace: "nowrap" }}>
                Step {index + 1}
              </Box>
              <TextField
                size="small"
                fullWidth
                placeholder="Step name"
                value={step.name}
                onChange={(e) => update(index, { name: e.target.value })}
              />
              <IconButton
                size="small"
                aria-label="Remove step"
                disabled={steps.length === 1}
                onClick={() => setSteps((prev) => prev.filter((_, i) => i !== index))}
              >
                <DeleteOutlinedIcon fontSize="small" />
              </IconButton>
            </Box>
            <Box sx={{ display: "grid", gap: 1.5, gridTemplateColumns: { xs: "1fr", md: "2fr 1fr 0.8fr" } }}>
              <Autocomplete
                multiple
                size="small"
                options={approvers}
                value={approvers.filter((p) => step.reviewer_ids.includes(p.id))}
                getOptionLabel={(p: PersonRef) => (p.job_title ? `${p.name} — ${p.job_title}` : p.name)}
                isOptionEqualToValue={(a, b) => a.id === b.id}
                onChange={(_, chosen) => update(index, { reviewer_ids: chosen.map((p) => p.id) })}
                renderInput={(params) => <TextField {...params} label="Reviewers" />}
              />
              <TextField
                select
                size="small"
                label="Who must approve"
                value={step.mode}
                onChange={(e) => update(index, { mode: e.target.value as "any" | "all" })}
              >
                <MenuItem value="any">Any one reviewer</MenuItem>
                <MenuItem value="all">Every reviewer</MenuItem>
              </TextField>
              <TextField
                type="number"
                size="small"
                label="Due in (days)"
                value={step.due_days ?? ""}
                onChange={(e) => update(index, { due_days: Number(e.target.value) || null })}
                slotProps={{ htmlInput: { min: 1, max: 365 } }}
              />
            </Box>
          </Box>
        ))}

        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
          <Button
            startIcon={<AddIcon fontSize="small" />}
            disabled={steps.length >= MAX_STEPS}
            onClick={() => setSteps((prev) => [...prev, { name: "", reviewer_ids: [], mode: "any", due_days: 2 }])}
            sx={{ textTransform: "none", color: "#0f766e" }}
          >
            Add step
          </Button>
          <TextField
            select
            size="small"
            label="Priority"
            value={priority}
            onChange={(e) => setPriority(e.target.value as Priority)}
            sx={{ minWidth: 160 }}
          >
            {PRIORITIES.map((p) => (
              <MenuItem key={p.value} value={p.value}>
                {p.label}
              </MenuItem>
            ))}
          </TextField>
        </Box>
      </Box>
    </CustomDialog>
  );
};

export default SubmitApprovalDialog;
