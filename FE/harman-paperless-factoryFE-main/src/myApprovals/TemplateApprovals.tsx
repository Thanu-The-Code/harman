import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { IconButton } from "@mui/material";
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import CustomAgGrid from "../base/aggrid";
import { ErrorState } from "../base/feedback";
import { useMyFormatApprovalsQuery } from "../api/formats.api";
import { formatDate } from "../utils/date";

interface Row {
  formatId: string;
  code: string;
  title: string;
  step: string;
  submittedBy: string;
  submittedOn: string;
  priority: string;
}

const ViewCell = ({ data, onView }: ICellRendererParams<Row> & { onView: (row: Row) => void }) =>
  data ? (
    <div className="action-cell">
      <IconButton className="eye-btn" size="small" aria-label={`Review ${data.code}`} onClick={() => onView(data)}>
        <VisibilityOutlinedIcon fontSize="small" />
      </IconButton>
    </div>
  ) : null;

/** Templates waiting for the signed-in person's release review. */
const TemplateApprovals = ({ search }: { search: string }) => {
  const navigate = useNavigate();
  const { data, isFetching, isError, error, refetch } = useMyFormatApprovalsQuery();

  const rows = useMemo<Row[]>(() => {
    const q = search.trim().toLowerCase();
    return (data?.approvals ?? [])
      .map(({ format_id, code, title, review }) => ({
        formatId: format_id,
        code,
        title,
        step: review.steps[review.current_step ?? 0]?.name ?? "",
        submittedBy: review.submitted_by?.name ?? "",
        submittedOn: formatDate(review.submitted_at),
        priority: review.priority ?? "normal",
      }))
      .filter((r) => !q || r.title.toLowerCase().includes(q) || r.code.toLowerCase().includes(q));
  }, [data, search]);

  const columns = useMemo<ColDef<Row>[]>(
    () => [
      { field: "code", headerName: "Code", flex: 0.9, minWidth: 120 },
      { field: "title", headerName: "Template", flex: 1.8, minWidth: 220, wrapText: true },
      { field: "step", headerName: "Your step", flex: 1.2, minWidth: 160 },
      { field: "submittedBy", headerName: "Submitted By", flex: 1, minWidth: 140 },
      { field: "submittedOn", headerName: "Submitted On", flex: 1, minWidth: 120 },
      { field: "priority", headerName: "Priority", flex: 0.7, minWidth: 100 },
      {
        headerName: "Action",
        width: 110,
        headerClass: "ag-center-header",
        cellRenderer: ViewCell,
        cellRendererParams: { onView: (row: Row) => navigate(`/builder/${row.formatId}`) },
      },
    ],
    [navigate],
  );

  if (isError) {
    return <ErrorState message={(error && "message" in error && error.message) || "Could not load template reviews."} onRetry={refetch} />;
  }
  return (
    <CustomAgGrid<Row>
      rowData={rows}
      columnDefs={columns}
      loading={isFetching && !data}
      emptyText="No templates are waiting for your review"
    />
  );
};

export default TemplateApprovals;
