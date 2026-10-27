/* eslint-disable react-refresh/only-export-components */
import PersonOutlinedIcon from "@mui/icons-material/PersonOutlined";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import CustomChip, { type ChipVariant } from "../base/chip/CustomChip";
import type { AuditEvent } from "../api/audit.api";
import { formatDate, formatDateTime } from "../utils/date";

const DateTimeCell = ({ data }: ICellRendererParams<AuditEvent>) => {
  if (!data) return null;
  const [, time] = formatDateTime(data.at).split(", ");
  return (
    <div className="datetime-cell">
      <div className="datetime-date">{formatDate(data.at)}</div>
      <div className="datetime-time">{time}</div>
    </div>
  );
};

const UserCell = ({ data }: ICellRendererParams<AuditEvent>) =>
  data ? (
    <div className="user-cell">
      <PersonOutlinedIcon />
      <span>{data.user ?? "System"}</span>
    </div>
  ) : null;

// the tones the audit API uses: "", accent, warn, danger
const TONE: Record<string, ChipVariant> = { danger: "orange", warn: "purple", accent: "green" };

const ActionCell = ({ data }: ICellRendererParams<AuditEvent>) =>
  data ? <CustomChip label={data.label || data.action} variant={TONE[data.tone] ?? "blue"} /> : null;

export const getActivityColumns = (): ColDef<AuditEvent>[] => [
  { headerName: "Date & Time", flex: 1, minWidth: 130, cellRenderer: DateTimeCell, autoHeight: true },
  { headerName: "User", flex: 1, minWidth: 140, cellRenderer: UserCell },
  { headerName: "Action", flex: 1.1, minWidth: 150, cellRenderer: ActionCell },
  { field: "module", headerName: "Module", flex: 1.1, minWidth: 150 },
  {
    headerName: "Details",
    flex: 2,
    minWidth: 260,
    wrapText: true,
    autoHeight: true,
    valueGetter: (p) => p.data?.summary || (p.data?.resource_type ? `${p.data.resource_type} ${p.data.resource_id ?? ""}` : "—"),
  },
];
