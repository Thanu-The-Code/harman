import { Tooltip } from "@mui/material";

export type Rag = "green" | "yellow" | "red";

// The tracking legend from the record process.
const RAG = {
  green: { color: "#22c55e", label: "Ok for final review" },
  yellow: { color: "#facc15", label: "Filling in progress" },
  red: { color: "#ef4444", label: "Needs to reverify with CFT" },
} as const;

/** The record's tracking colour, with the API's label as the tooltip. */
const RagDot = ({ rag, label, showLabel = false }: { rag?: Rag | null; label?: string | null; showLabel?: boolean }) => {
  if (!rag || !(rag in RAG)) return null;
  const text = label || RAG[rag].label;
  return (
    <Tooltip title={text} arrow>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
        <span
          aria-label={text}
          role="img"
          style={{ width: 10, height: 10, borderRadius: "50%", background: RAG[rag].color, flexShrink: 0 }}
        />
        {showLabel && <span style={{ fontSize: 12 }}>{text}</span>}
      </span>
    </Tooltip>
  );
};

export default RagDot;
