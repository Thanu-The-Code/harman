/* eslint-disable react-refresh/only-export-components */
import { IconButton } from "@mui/material";
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { STAGE_STEP, type MyApprovalItem } from "../api/approvals.api";
import { formatDate, formatDateTime } from "../utils/date";

interface ActionProps extends ICellRendererParams<MyApprovalItem> {
  onView: (row: MyApprovalItem) => void;
}

const ActionCell = ({ data, onView }: ActionProps) =>
  data ? (
    <div className="action-cell">
      <IconButton className="eye-btn" size="small" aria-label={`Open ${data.document_name}`} onClick={() => onView(data)}>
        <VisibilityOutlinedIcon fontSize="small" />
      </IconButton>
    </div>
  ) : null;

export const getApprovalColumns = ({
  onView,
  overdue = false,
}: {
  onView: (row: MyApprovalItem) => void;
  /** the Overdue tab: every due date is past (the server decides) */
  overdue?: boolean;
}): ColDef<MyApprovalItem>[] => [
  { field: "document_name", headerName: "Document Name", flex: 1.6, minWidth: 220, wrapText: true, autoHeight: true },
  { headerName: "Department", flex: 1.1, minWidth: 150, valueGetter: (p) => p.data?.department ?? "—" },
  { headerName: "Step", flex: 1.3, minWidth: 170, valueGetter: (p) => (p.data ? STAGE_STEP[p.data.stage] ?? p.data.stage : "") },
  { headerName: "Assigned By", flex: 1, minWidth: 130, valueGetter: (p) => p.data?.assigned_by ?? "—" },
  { headerName: "Submitted On", flex: 1, minWidth: 120, valueGetter: (p) => formatDate(p.data?.submitted_on) },
  {
    headerName: "Due",
    flex: 1.1,
    minWidth: 150,
    valueGetter: (p) => formatDateTime(p.data?.due_at),
    cellStyle: overdue ? { color: "#dc2626", fontWeight: 600 } : undefined,
  },
  {
    headerName: "Action",
    width: 110,
    headerClass: "ag-center-header",
    cellRenderer: ActionCell,
    cellRendererParams: { onView },
  },
];
