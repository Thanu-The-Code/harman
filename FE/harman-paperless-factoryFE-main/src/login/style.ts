import type { SxProps, Theme } from "@mui/material/styles";

const TEAL = "#0CB9AF";
const DARK_TEAL = "#14918a";
const NAVY = "#0f1729";
const MUTED = "#6b7280";

export const loginStyles: SxProps<Theme> = {
  minHeight: "100vh",
  boxSizing: "border-box",
  padding: "20px",
  background: "#fff",
  fontFamily: '"Outfit", "Plus Jakarta Sans", "Inter", Roboto, sans-serif',
  color: NAVY,

  "& .login-layout": {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)",
    gap: "24px",
    minHeight: "940px",
    // minWidth: "100%",
    "@media (max-width: 900px)": { gridTemplateColumns: "1fr" },
  },

  /* ---------- left: illustration ---------- */
  "& .login-hero": {
    position: "relative",
    // width: "705px",
    display: "flex",
    flexDirection: "column",
    justifyContent: "space-between",
    gap: "24px",
    padding: "54px 20px 20px",
    borderRadius: "8px",
    overflow: "hidden",
    // backgroundColor: "#f3fbfb",
    backgroundSize: "cover",
    backgroundPosition: "center",
    backgroundRepeat: "no-repeat",
    "@media (max-width: 900px)": { display: "none" },
  },
  "& .hero-title": { margin: 0, fontSize: 40, fontWeight: 700, lineHeight: 1.2 },
  "& .hero-title span": { color: TEAL },
  "& .hero-subtitle": { margin: "10px 0 0", fontSize: "18.5px", lineHeight: "27.65px", color: "#45556C" },

  "& .hero-features": { display: "grid",  gridTemplateColumns: "repeat(3, minmax(0, 1fr))" },
  "& .hero-feature": {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    padding: "0 14px",
    "&:first-of-type": { paddingLeft: 0 },
    "&:not(:last-of-type)": { borderRight: "1px solid #E2E8F0" },
  },
  "& .feature-icon": {
    width: 34,
    height: 34,
    borderRadius: "4px",
    background: "#EAF8F9",
    color: TEAL,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
    "& svg": { fontSize: 17 },
  },
  "& .feature-title": { fontSize: 14, fontWeight: 600, color: NAVY, lineHeight: "26px" },
  "& .feature-text": { fontSize: 12, color: "#45556C", lineHeight: "16px", marginTop: "2px" },

  /* ---------- right: form ---------- */
  "& .login-form-side": { display: "flex", alignItems: "center", justifyContent: "center", padding: "24px" },
  "& .login-card": { width: "100%", maxWidth: 400 },
  "& .brand": { textAlign: "center", marginBottom: "44px" },
  "& .brand-name": { margin: 0, fontSize: 36, fontWeight: 600, lineHeight: 1.2, color: NAVY },
  "& .brand-sub": { margin: "4px 0 0", fontSize: 18, color: "#58456C" },
  "& .login-heading": { margin: "0 0 22px", textAlign: "center", fontSize: 23, fontWeight: 600 },
  "& .login-notice": {
    margin: "-8px 0 16px", padding: "10px 12px", borderRadius: 8, fontSize: 13,
    background: "#fff7ed", border: "1px solid #fed7aa", color: "#9a3412",
  },

  "& .login-form": { display: "flex", flexDirection: "column", gap: "18px" },
  "& .login-field .form-field-label": { fontSize: 17, fontWeight: 500, color: "#232F3D" },
  "& .login-field .MuiOutlinedInput-root": { background: "#f6f8fa" },
  "& .login-field .MuiOutlinedInput-input": { padding: "12px 14px", fontSize: 14 },
  "& .eye-btn": { color: MUTED, padding: "4px" },

  "& .login-error": { margin: 0, fontSize: 12, color: "#dc2626" },
  "& .login-btn": {
    marginTop: "6px",
    height: 44,
    textTransform: "none",
    fontSize: 15,
    fontWeight: 500,
    borderRadius: "6px",
    background: DARK_TEAL,
    boxShadow: "none",
    "&:hover": { background: "#0f7f79", boxShadow: "none" },
    "&.Mui-disabled": { background: "#8fcfc9", color: "#fff" },
  },
  "& .login-footer": { margin: "18px 0 0", textAlign: "center", fontSize: 12, color: MUTED },
};