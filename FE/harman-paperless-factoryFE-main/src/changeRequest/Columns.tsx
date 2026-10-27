/* eslint-disable react-refresh/only-export-components */
import { IconButton } from "@mui/material";
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import CustomChip, { type ChipVariant } from "../base/chip/CustomChip";
import type { Dcr, Rcr } from "../api/changeRequests.api";
import { formatDate } from "../utils/date";

const STATUS_CHIP: Record<string, ChipVariant> = {
  submitted: "blue",
  under_review: "purple",
  open: "blue",
  approved: "green",
  implemented: "green",
  rejected: "orange",
  not_approved: "orange",
};

const StatusCell = ({ data }: ICellRendererParams<Dcr | Rcr>) =>
  data ? <CustomChip label={data.status_label} variant={STATUS_CHIP[data.status] ?? "gray"} /> : null;

const viewCell = <T,>(onView: (row: T) => void) =>
  function ViewCell({ data }: ICellRendererParams<T>) {
    return data ? (
      <div className="action-cell">
        <IconButton className="eye-btn" size="small" aria-label="View change request" onClick={() => onView(data)}>
          <VisibilityOutlinedIcon fontSize="small" />
        </IconButton>
      </div>
    ) : null;
  };

const TitleCell = ({ data }: ICellRendererParams<Dcr | Rcr>) =>
  data ? (
    <div style={{ lineHeight: 1.35, padding: "6px 0" }}>
      <div>{data.title}</div>
      <div style={{ fontSize: 11, color: "#6b7280" }}>{data.number}</div>
    </div>
  ) : null;

/** Format change requests (DCR). */
export const getDcrColumns = ({ onView }: { onView: (row: Dcr) => void }): ColDef<Dcr>[] => [
  { headerName: "Request", flex: 2, minWidth: 240, cellRenderer: TitleCell, autoHeight: true },
  {
    headerName: "Format",
    flex: 1.4,
    minWidth: 170,
    valueGetter: (p) => (p.data?.format ? `${p.data.format.code} rev ${p.data.format.revision}` : p.data?.kind_label ?? ""),
  },
  { headerName: "Team", flex: 1.1, minWidth: 140, valueGetter: (p) => p.data?.team?.name ?? "—" },
  { headerName: "Raised By", flex: 1, minWidth: 130, valueGetter: (p) => p.data?.raised_by?.name ?? "—" },
  { headerName: "Raised On", flex: 0.9, minWidth: 120, valueGetter: (p) => formatDate(p.data?.raised_at) },
  { headerName: "Status", flex: 0.9, minWidth: 130, cellRenderer: StatusCell },
  { headerName: "Action", width: 100, headerClass: "ag-center-header", cellRenderer: viewCell<Dcr>(onView) },
];

/** Record change requests (RCR). */
export const getRcrColumns = ({ onView }: { onView: (row: Rcr) => void }): ColDef<Rcr>[] => [
  { headerName: "Request", flex: 2, minWidth: 240, cellRenderer: TitleCell, autoHeight: true },
  {
    headerName: "Record",
    flex: 1.5,
    minWidth: 190,
    valueGetter: (p) => (p.data?.record ? `${p.data.record.number}` : "—"),
  },
  { headerName: "Department", flex: 1.1, minWidth: 140, valueGetter: (p) => p.data?.record?.department ?? "—" },
  { headerName: "Assigned To", flex: 1, minWidth: 130, valueGetter: (p) => p.data?.assigned_to?.name ?? "—" },
  { headerName: "Raised On", flex: 0.9, minWidth: 120, valueGetter: (p) => formatDate(p.data?.raised_at) },
  { headerName: "Status", flex: 0.9, minWidth: 130, cellRenderer: StatusCell },
  { headerName: "Action", width: 100, headerClass: "ag-center-header", cellRenderer: viewCell<Rcr>(onView) },
];
