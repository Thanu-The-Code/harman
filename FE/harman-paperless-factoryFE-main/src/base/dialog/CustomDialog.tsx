import React from "react";
import { Button, Dialog, IconButton } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import { customDialogStyles } from "./style";

interface Props {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  subtitle?: React.ReactNode;
  children: React.ReactNode;
  confirmText?: string;
  cancelText?: string;
  confirmDisabled?: boolean;
  maxWidth?: "xs" | "sm" | "md";
}

const CustomDialog = ({
  open,
  onClose,
  onConfirm,
  title,
  subtitle,
  children,
  confirmText = "Confirm",
  cancelText = "Cancel",
  confirmDisabled = false,
  maxWidth = "sm",
}: Props) => (
  <Dialog open={open} onClose={onClose} fullWidth maxWidth={maxWidth} sx={customDialogStyles}>
    <div className="dialog-header">
      <div>
        <h2 className="dialog-title">{title}</h2>
        {subtitle && <p className="dialog-subtitle">{subtitle}</p>}
      </div>
      <IconButton className="dialog-close" aria-label="Close" onClick={onClose}>
        <CloseIcon fontSize="small" />
      </IconButton>
    </div>

    <div className="dialog-body">{children}</div>

    <div className="dialog-footer">
      <Button className="dialog-btn cancel-btn" onClick={onClose}>
        {cancelText}
      </Button>
      <Button
        className="dialog-btn confirm-btn"
        variant="contained"
        disabled={confirmDisabled}
        onClick={onConfirm}
      >
        {confirmText}
      </Button>
    </div>
  </Dialog>
);

export default CustomDialog;