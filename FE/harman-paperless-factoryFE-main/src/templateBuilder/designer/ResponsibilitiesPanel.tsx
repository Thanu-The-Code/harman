import { useMemo } from "react";
import { Autocomplete, MenuItem, TextField } from "@mui/material";
import {
  FREQUENCY_OPTIONS,
  type Frequency,
  type PersonRef,
  type ResponsibilityPeople,
  type TemplateFolder,
} from "../../api/formats.api";

export interface Responsibilities {
  frequency: Frequency;
  process_owner_id: string;
  overall_process_owner_id: string;
  qms_coordinator_id: string;
  cft_member_ids: string[];
  cft_target_days: number;
  work_instruction_ref: string;
  work_instruction: string;
  storage_path: string;
}

interface Props {
  value: Responsibilities;
  onChange: (patch: Partial<Responsibilities>) => void;
  people?: ResponsibilityPeople;
  folders?: TemplateFolder[];
  storagePreview?: string;
  disabled?: boolean;
}

const flattenFolders = (nodes: TemplateFolder[] = []): string[] =>
  nodes.flatMap((n) => [n.path, ...flattenFolders(n.children)]);

const personLabel = (p: PersonRef) => (p.job_title ? `${p.name} — ${p.job_title}` : p.name);

/** A single responsibility. Blank is allowed: the approver is then chosen when a record is submitted. */
const PersonSelect = ({
  label,
  helper,
  options = [],
  value,
  onChange,
  disabled,
}: {
  label: string;
  helper: string;
  options?: PersonRef[];
  value: string;
  onChange: (id: string) => void;
  disabled?: boolean;
}) => (
  <TextField
    select
    size="small"
    fullWidth
    label={label}
    helperText={helper}
    value={options.some((p) => p.id === value) ? value : ""}
    onChange={(e) => onChange(e.target.value)}
    disabled={disabled}
  >
    <MenuItem value="">
      <em>Chosen when the record is submitted</em>
    </MenuItem>
    {options.map((p) => (
      <MenuItem key={p.id} value={p.id}>
        {personLabel(p)}
      </MenuItem>
    ))}
  </TextField>
);

const ResponsibilitiesPanel = ({ value, onChange, people, folders, storagePreview, disabled }: Props) => {
  const folderOptions = useMemo(() => flattenFolders(folders), [folders]);
  const cftOptions = people?.cft_members ?? [];
  const selectedCft = cftOptions.filter((p) => value.cft_member_ids.includes(p.id));

  return (
    <div className="designer-card">
      <h2 className="card-title">Process & responsibilities</h2>
      <p className="card-caption">
        Who fills and approves records of this template, how often, and where approved records are filed. A role left
        blank is chosen by the person submitting each record.
      </p>

      <div className="field-grid-3">
        <TextField
          select
          size="small"
          fullWidth
          label="Frequency"
          helperText="Sets the record period and the date / month folders"
          value={value.frequency}
          onChange={(e) => onChange({ frequency: e.target.value as Frequency })}
          disabled={disabled}
        >
          {FREQUENCY_OPTIONS.map((f) => (
            <MenuItem key={f.value} value={f.value}>
              {f.label}
            </MenuItem>
          ))}
        </TextField>
        <PersonSelect
          label="Process Owner"
          helper="Fills the record, approves step 1 and takes the final decision"
          options={people?.process_owner}
          value={value.process_owner_id}
          onChange={(id) => onChange({ process_owner_id: id })}
          disabled={disabled}
        />
        <PersonSelect
          label="Overall Process Owner"
          helper="Approves step 2, clears N-OK flags, files records"
          options={people?.overall_process_owner}
          value={value.overall_process_owner_id}
          onChange={(id) => onChange({ overall_process_owner_id: id })}
          disabled={disabled}
        />
        <Autocomplete
          multiple
          size="small"
          options={cftOptions}
          value={selectedCft}
          getOptionLabel={personLabel}
          isOptionEqualToValue={(a, b) => a.id === b.id}
          onChange={(_, chosen) => onChange({ cft_member_ids: chosen.map((p) => p.id) })}
          disabled={disabled}
          renderInput={(params) => (
            <TextField {...params} label="Quality CFT members" helperText="Every member reviews jointly" />
          )}
        />
        <TextField
          type="number"
          size="small"
          fullWidth
          label="CFT target (days)"
          helperText="Joint review deadline after the OPO approves"
          value={value.cft_target_days}
          onChange={(e) => onChange({ cft_target_days: Math.max(1, Number(e.target.value) || 1) })}
          slotProps={{ htmlInput: { min: 1, max: 60 } }}
          disabled={disabled}
        />
        <PersonSelect
          label="QMS Coordinator"
          helper="Approves change requests for this template"
          options={people?.qms_coordinator}
          value={value.qms_coordinator_id}
          onChange={(id) => onChange({ qms_coordinator_id: id })}
          disabled={disabled}
        />
      </div>

      <div className="field-grid" style={{ marginTop: 16 }}>
        <TextField
          size="small"
          fullWidth
          label="Work instruction reference"
          placeholder="WI-PQ-012 rev 3"
          value={value.work_instruction_ref}
          onChange={(e) => onChange({ work_instruction_ref: e.target.value })}
          disabled={disabled}
        />
        <Autocomplete
          freeSolo
          size="small"
          options={folderOptions}
          value={value.storage_path}
          onInputChange={(_, path) => onChange({ storage_path: path })}
          disabled={disabled}
          renderInput={(params) => (
            <TextField
              {...params}
              label="Template folder / filing root"
              helperText={storagePreview ? `Records will be filed in: ${storagePreview}` : "Records / <team> / <code> when blank"}
            />
          )}
        />
        <TextField
          className="span-2"
          size="small"
          fullWidth
          multiline
          minRows={2}
          label="Work instruction"
          placeholder="How the record is to be filled — shown to the person filling it"
          value={value.work_instruction}
          onChange={(e) => onChange({ work_instruction: e.target.value })}
          disabled={disabled}
        />
      </div>
    </div>
  );
};

export default ResponsibilitiesPanel;
