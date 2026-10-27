import { useRef, useState } from "react";
import { Button, IconButton, TextField } from "@mui/material";
import FileUploadOutlinedIcon from "@mui/icons-material/FileUploadOutlined";
import AttachFileIcon from "@mui/icons-material/AttachFile";
import DeleteOutlinedIcon from "@mui/icons-material/DeleteOutlined";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import { toast } from "react-toastify";
import CollapsibleCard from "./CollapsibleCard";
import {
  useDeleteAttachmentMutation,
  useUploadAttachmentMutation,
  useUploadScanMutation,
  type RecordDetail,
} from "../api/records.api";
import { getApiErrorMessage } from "../api/errors";
import { openAuthedFile } from "../utils/openAuthedFile";
import { formatDateTime } from "../utils/date";

const kb = (size: number) => (size > 1024 * 1024 ? `${(size / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(size / 1024))} KB`);

/** The paper record (optional scan) and any supporting photos or documents. */
const RecordEvidence = ({ record, canEdit }: { record: RecordDetail; canEdit: boolean }) => {
  const scanInput = useRef<HTMLInputElement>(null);
  const attachInput = useRef<HTMLInputElement>(null);
  const [caption, setCaption] = useState("");
  const [uploadScan, { isLoading: scanning }] = useUploadScanMutation();
  const [uploadAttachment, { isLoading: attaching }] = useUploadAttachmentMutation();
  const [deleteAttachment] = useDeleteAttachmentMutation();

  const onScan = async (file?: File) => {
    if (!file) return;
    try {
      await uploadScan({ id: record.id, file }).unwrap();
      toast.success(`Scan "${file.name}" attached. It will be the record's document.`);
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Could not attach the scan."));
    } finally {
      if (scanInput.current) scanInput.current.value = "";
    }
  };

  const onAttach = async (file?: File) => {
    if (!file) return;
    try {
      await uploadAttachment({ id: record.id, file, caption: caption.trim() || undefined }).unwrap();
      setCaption("");
      toast.success(`"${file.name}" attached.`);
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Could not attach the file."));
    } finally {
      if (attachInput.current) attachInput.current.value = "";
    }
  };

  const onDelete = async (attachmentId: string, name: string) => {
    try {
      await deleteAttachment({ id: record.id, attachmentId }).unwrap();
      toast.success(`"${name}" removed.`);
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Could not remove the file."));
    }
  };

  return (
    <CollapsibleCard
      title="The filled record"
      subtitle="Filled it on paper? Attach the scan or photograph. Filled it here? Nothing to attach — a PDF of this form is produced when you submit."
    >
      <div className="record-body">
        <p className="record-note">
          {record.entry_mode === "hardcopy" && record.document_id ? (
            <>
              A scanned paper record is attached and will be the record's document.{" "}
              <Button size="small" startIcon={<OpenInNewIcon fontSize="small" />} onClick={() => openAuthedFile(`api/documents/${record.document_id}/file`)}>
                View scan
              </Button>
            </>
          ) : (
            "Nothing attached — which is correct for a form filled on this screen."
          )}
        </p>
        <input ref={scanInput} type="file" accept="image/*,application/pdf" hidden onChange={(e) => onScan(e.target.files?.[0])} />
        {/* the hard copy goes with the filling: once submitted (re-verification included) it is fixed */}
        <Button
          className="attach-btn"
          startIcon={<FileUploadOutlinedIcon fontSize="small" />}
          disabled={!canEdit || record.stage !== "filling" || scanning}
          title={record.stage !== "filling" ? "The hard copy can only be attached while the record is being filled." : undefined}
          onClick={() => scanInput.current?.click()}
        >
          {scanning
            ? "Attaching…"
            : record.entry_mode === "hardcopy" && record.document_id
              ? "Replace the scanned hard copy"
              : "Attach the scanned hard copy (optional)"}
        </Button>

        <div className="attachments">
          <div className="attachments-title">Supporting photos and documents</div>
          {record.attachments.length === 0 && <p className="record-note">None yet.</p>}
          {record.attachments.map((a) => (
            <div className="attachment-row" key={a.id}>
              <AttachFileIcon fontSize="small" />
              <button type="button" className="attachment-link" onClick={() => openAuthedFile(a.href || `api/records/${record.id}/attachments/${a.id}`)}>
                {a.filename}
              </button>
              <span className="attachment-meta">
                {a.caption ? `${a.caption} · ` : ""}
                {kb(a.size)} · {a.uploaded_by?.name ?? ""} · {formatDateTime(a.uploaded_at)}
              </span>
              {canEdit && (
                <IconButton size="small" aria-label={`Remove ${a.filename}`} onClick={() => onDelete(a.id, a.filename)}>
                  <DeleteOutlinedIcon fontSize="small" />
                </IconButton>
              )}
            </div>
          ))}
          {canEdit && (
            <div className="attachment-add">
              <TextField size="small" placeholder="Caption (optional)" value={caption} onChange={(e) => setCaption(e.target.value)} />
              <input ref={attachInput} type="file" hidden onChange={(e) => onAttach(e.target.files?.[0])} />
              <Button size="small" variant="outlined" disabled={attaching} onClick={() => attachInput.current?.click()}>
                {attaching ? "Uploading…" : "Add file"}
              </Button>
            </div>
          )}
        </div>
      </div>
    </CollapsibleCard>
  );
};

export default RecordEvidence;
