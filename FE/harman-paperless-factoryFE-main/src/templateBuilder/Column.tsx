/* eslint-disable react-refresh/only-export-components */
import { IconButton } from "@mui/material";
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import type { BuilderRow } from "../constants/types";

interface ActionProps extends ICellRendererParams<BuilderRow> {
  onView: (row: BuilderRow) => void;
}

const ActionCell = ({ data, onView }: ActionProps) =>
  data ? (
    <div className="action-cell">
      <IconButton className="eye-btn" size="small" aria-label={`View ${data.name}`} onClick={() => onView(data)}>
        <VisibilityOutlinedIcon fontSize="small" />
      </IconButton>
    </div>
  ) : null;

export const getBuilderColumns = ({ onView }: { onView: (row: BuilderRow) => void }): ColDef<BuilderRow>[] => [
  // Figma: Document Name, Department, Type, Last Update, Action (the code shows on hover)
  { field: "name", headerName: "Document Name", flex: 3, minWidth: 240, tooltipValueGetter: (p) => p.data?.code },
  { field: "department", headerName: "Department", flex: 1.6, minWidth: 160 },
  { field: "type", headerName: "Type", flex: 1, minWidth: 110 },
  { field: "lastUpdate", headerName: "Last Update", flex: 1.2, minWidth: 130 },
  {
    headerName: "Action",
    width: 110,
    headerClass: "ag-center-header",
    cellRenderer: ActionCell,
    cellRendererParams: { onView },
  },
];