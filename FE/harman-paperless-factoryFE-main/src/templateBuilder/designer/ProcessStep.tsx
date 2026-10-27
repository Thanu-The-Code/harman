import { useRef } from "react";
import { Button } from "@mui/material";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import { toast } from "react-toastify";
import ResponsibilitiesPanel, { type Responsibilities } from "./ResponsibilitiesPanel";
import {
  useResponsibilityPeopleQuery,
  useTemplateFoldersQuery,
  useUploadBlankMutation,
  type FormatDetail,
} from "../../api/formats.api";
import { getApiErrorMessage } from "../../api/errors";
import { axiosInstance } from "../../helpers";

interface Props {
  format: FormatDetail;
  value: Responsibilities;
  onChange: (patch: Partial<Responsibilities>) => void;
  disabled: boolean;
}

/**
 * The second step of the designer (Continue): who fills and approves records of the
 * template, how often, where they are filed, and the blank form people can print.
 */
const ProcessStep = ({ format, value, onChange, disabled }: Props) => {
  const { data: people } = useResponsibilityPeopleQuery();
  const { data: foldersData } = useTemplateFoldersQuery();
  const [uploadBlank, { isLoading: uploading }] = useUploadBlankMutation();
  const blankInput = useRef<HTMLInputElement>(null);

  const recorded = format.fields ?? [];
  const limited = recorded.filter((f) => f.spec_min !== null || f.spec_max !== null || f.spec_text);

  const attach = async (file?: File) => {
    if (!file) return;
    try {
      await uploadBlank({ id: format.id, file }).unwrap();
      toast.success(`Blank form "${file.name}" attached.`);
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Could not attach the blank form."));
    } finally {
      if (blankInput.current) blankInput.current.value = "";
    }
  };

  const openBlank = async () => {
    try {
      const res = await axiosInstance.get<Blob>(`api/formats/${format.id}/blank`, { params: { inline: true }, responseType: "blob" });
      window.open(URL.createObjectURL(res.data), "_blank", "noopener");
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Could not open the blank form."));
    }
  };

  return (
    <div className="process-step">
      <div className="designer-card">
        <h2 className="card-title">What this template records</h2>
        <p className="card-caption">
          {recorded.length} {recorded.length === 1 ? "entry" : "entries"} to fill in
          {limited.length ? `, ${limited.length} judged against a limit or a conforming value` : ""}. Go back to the
          design to change them.
        </p>
        {recorded.length > 0 && (
          <ul className="recorded-list">
            {recorded.slice(0, 12).map((f) => (
              <li key={f.id}>
                <span>{f.label}</span>
                <span className="muted">{f.spec_label && f.spec_label !== "-" ? f.spec_label : f.field_type}</span>
              </li>
            ))}
            {recorded.length > 12 && <li className="muted">and {recorded.length - 12} more</li>}
          </ul>
        )}
      </div>

      <ResponsibilitiesPanel
        value={value}
        onChange={onChange}
        people={people}
        folders={foldersData?.folders}
        storagePreview={format.storage_preview}
        disabled={disabled}
      />

      <div className="designer-card">
        <h2 className="card-title">Blank form</h2>
        <p className="card-caption">The printable sheet (PDF or picture) shown in the Resources library, for filling on paper.</p>
        <div className="blank-row">
          {format.has_blank ? (
            <>
              <span>Attached ({format.blank_mime ?? "file"})</span>
              <Button size="small" onClick={openBlank} sx={{ textTransform: "none" }}>
                View
              </Button>
            </>
          ) : (
            <span className="muted">None attached</span>
          )}
          <input ref={blankInput} type="file" hidden accept="application/pdf,image/*" onChange={(e) => attach(e.target.files?.[0])} />
          <Button
            size="small"
            variant="outlined"
            startIcon={<UploadFileOutlinedIcon fontSize="small" />}
            disabled={uploading || disabled}
            onClick={() => blankInput.current?.click()}
            sx={{ textTransform: "none" }}
          >
            {format.has_blank ? "Replace" : "Attach"}
          </Button>
        </div>
      </div>
    </div>
  );
};

export default ProcessStep;
