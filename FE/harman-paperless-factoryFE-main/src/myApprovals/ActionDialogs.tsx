import { useState, type ReactNode } from "react";
import CustomDialog from "../base/dialog/CustomDialog";
import CustomTextArea from "../base/dialog/CustomTextarea";
import SignaturePad, { type SignatureValue } from "../base/signature/SignaturePad";

const NOTE_PLACEHOLDER = "Recorded in the status trail and the activity log";

export interface DecisionResult {
  note: string;
  signature: SignatureValue | null;
}

interface Props {
  open: boolean;
  onClose: () => void;
  onConfirm: (result: DecisionResult) => void;
  title: string;
  subtitle?: ReactNode;
  confirmText: string;
  noteLabel: string;
  /** A negative answer must say why. */
  noteRequired?: boolean;
  /** The step is signed: the person signs here. */
  requiresSignature?: boolean;
  signerName?: string;
  busy?: boolean;
}

/**
 * Every answer on an approval step goes through this: approve (and sign),
 * agree / object at the joint review, return for correction, send back to
 * the CFT, close an N-OK flag.
 */
export const DecisionDialog = ({
  open,
  onClose,
  onConfirm,
  title,
  subtitle,
  confirmText,
  noteLabel,
  noteRequired = false,
  requiresSignature = false,
  signerName,
  busy = false,
}: Props) => {
  const [note, setNote] = useState("");
  const [signature, setSignature] = useState<SignatureValue | null>(null);

  const close = () => {
    setNote("");
    setSignature(null);
    onClose();
  };

  const ready = (!noteRequired || note.trim().length > 0) && (!requiresSignature || signature !== null);

  return (
    <CustomDialog
      open={open}
      onClose={close}
      title={title}
      subtitle={subtitle}
      confirmText={busy ? "Saving…" : confirmText}
      confirmDisabled={!ready || busy}
      onConfirm={() => onConfirm({ note: note.trim(), signature })}
    >
      <CustomTextArea
        label={noteLabel}
        optional={!noteRequired}
        value={note}
        onChange={setNote}
        placeholder={NOTE_PLACEHOLDER}
        rows={requiresSignature ? 3 : 5}
      />
      {requiresSignature && open && (
        <div style={{ marginTop: 12 }}>
          <div className="field-label" style={{ fontSize: 12, marginBottom: 6 }}>
            Signature
          </div>
          <SignaturePad onChange={setSignature} defaultName={signerName} />
        </div>
      )}
    </CustomDialog>
  );
};
