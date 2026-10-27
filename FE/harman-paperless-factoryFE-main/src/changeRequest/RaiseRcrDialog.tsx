import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "react-toastify";
import CustomDialog from "../base/dialog/CustomDialog";
import CustomTextField from "../base/dialog/CustomTextField";
import CustomTextArea from "../base/dialog/CustomTextarea";
import { useRaiseRcrMutation } from "../api/changeRequests.api";
import { getApiErrorMessage } from "../api/errors";

/** Ask for a change to a filled record; it goes to the format's QMS Coordinator. */
const RaiseRcrDialog = ({ open, onClose, record }: { open: boolean; onClose: () => void; record: { id: string; number: string } }) => {
  const navigate = useNavigate();
  const [raise, { isLoading }] = useRaiseRcrMutation();
  const [title, setTitle] = useState(`Change to ${record.number}`);
  const [reason, setReason] = useState("");

  const submit = async () => {
    try {
      const rcr = await raise({ record_id: record.id, title: title.trim() || undefined, reason: reason.trim() }).unwrap();
      toast.success(`${rcr.number} raised${rcr.assigned_to ? ` and assigned to ${rcr.assigned_to.name}` : ""}.`);
      onClose();
      navigate(`/change-request/rcr/${rcr.id}`);
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Could not raise the change request."));
    }
  };

  return (
    <CustomDialog
      open={open}
      onClose={onClose}
      onConfirm={submit}
      title="Request a change to this record"
      subtitle={<>For <b>{record.number}</b>. It is decided before anything is changed.</>}
      confirmText={isLoading ? "Sending…" : "Raise request"}
      confirmDisabled={isLoading || !reason.trim()}
    >
      <CustomTextField label="Title" value={title} onChange={setTitle} />
      <CustomTextArea label="What has to change, and why?" value={reason} onChange={setReason} rows={5} />
    </CustomDialog>
  );
};

export default RaiseRcrDialog;
