import React from "react";
import { Button, Dialog } from "@mui/material";
import type { SxProps, Theme } from "@mui/material/styles";
import CheckIcon from "@mui/icons-material/Check";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";

const TEAL = "#14b8a6";
const BORDER = "#e5e7eb";
const MUTED = "#6b7280";

const paperSx = (width: number): SxProps<Theme> => ({
  width: "100%",
  maxWidth: width,
  borderRadius: "12px",
  boxShadow: "0 12px 40px rgba(15, 23, 42, 0.18)",
  fontFamily: '"Plus Jakarta Sans", "Inter", Roboto, sans-serif',
  color: "#111827",
  overflow: "hidden",
});

const footerSx: SxProps<Theme> = {
  display: "flex",
  justifyContent: "flex-end",
  gap: "12px",
  padding: "14px 20px",
  borderTop: `1px solid ${BORDER}`,
};

const btnBase: SxProps<Theme> = {
  textTransform: "none",
  fontSize: 14,
  fontWeight: 600,
  borderRadius: "6px",
  padding: "7px 20px",
  boxShadow: "none",
  whiteSpace: "nowrap",
};

const outlineBtnSx: SxProps<Theme> = {
  ...btnBase,
  color: MUTED,
  background: "#fff",
  border: `1px solid ${BORDER}`,
  "&:hover": { background: "#f9fafb", borderColor: "#d1d5db" },
};

const primaryBtnSx: SxProps<Theme> = {
  ...btnBase,
  color: "#fff",
  background: TEAL,
  "&:hover": { background: "#0f9e8e", boxShadow: "none" },
};

/* ---------- 3. approval started ---------- */
interface StartedProps {
  open: boolean;
  onViewDocuments: () => void;
  onDone: () => void;
}

export const ApprovalStartedDialog: React.FC<StartedProps> = ({ open, onViewDocuments, onDone }) => (
  <Dialog open={open} slotProps={{ paper: { sx: paperSx(520) } }}>
    <div style={{ padding: "28px 28px 22px", textAlign: "center" }}>
      <span
        style={{
          width: 64,
          height: 64,
          borderRadius: 18,
          background: "#e6f7f5",
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <span
          style={{
            width: 40,
            height: 40,
            borderRadius: 10,
            background: TEAL,
            color: "#fff",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <CheckIcon sx={{ fontSize: 26 }} />
        </span>
      </span>
      <h2 style={{ margin: "14px 0 6px", fontSize: 20, fontWeight: 700 }}>
        Approval process started!
      </h2>
      <p style={{ margin: "0 auto", maxWidth: 300, fontSize: 14, color: MUTED, lineHeight: 1.5 }}>
        The form has been submitted and sent to the first approver in your approval route.
      </p>
      <div
        style={{
          margin: "20px 0 0",
          padding: "12px 14px",
          background: "#eaf5fe",
          borderRadius: 8,
          textAlign: "left",
          display: "flex",
          gap: 10,
          alignItems: "flex-start",
          fontSize: 14,
          color: MUTED,
          lineHeight: 1.5,
        }}
      >
        <InfoOutlinedIcon sx={{ fontSize: 20, color: "#2f80ed", marginTop: "1px" }} />
        <span>
          You’ll be notified about the status of this form. Track its progress in{" "}
          <a
            href="/my-forms"
            style={{ color: "#2f80ed", textDecoration: "none" }}
            onClick={(e) => {
              e.preventDefault();
              onViewDocuments();
            }}
          >
            My Documents.
          </a>
        </span>
      </div>
    </div>
    <div style={{ ...(footerSx as object) }}>
      <Button sx={outlineBtnSx} onClick={onViewDocuments}>
        View in My Documents
      </Button>
      <Button sx={primaryBtnSx} variant="contained" onClick={onDone}>
        Done
      </Button>
    </div>
  </Dialog>
);