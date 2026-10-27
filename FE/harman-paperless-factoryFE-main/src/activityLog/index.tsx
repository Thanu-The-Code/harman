import { useMemo, useState } from "react";
import { Box } from "@mui/material";
import PageHeader from "../base/pageHeader";
import CustomSearchBox from "../base/search/CustomSearch";
import CustomSelect from "../base/dropdown/CustomSelect";
import CustomAgGrid from "../base/aggrid";
import CustomPagination from "../base/pagination";
import { ErrorState } from "../base/feedback";
import { activityLogStyles } from "./style";
import { getActivityColumns } from "./Column";
import CustomDateRange, { type DateRange } from "../base/date/DateRange";
import { useAuditModulesQuery, useAuditQuery, type AuditEvent } from "../api/audit.api";
import { useDebouncedValue } from "../hooks/useDebouncedValue";

const PAGE_SIZE_OPTIONS = [10, 25, 50];

/** The audit trail: who did what, when (last 365 days by default when a range is open). */
const ActivityLog = () => {
  const [search, setSearch] = useState("");
  const [range, setRange] = useState<DateRange>({ from: "", to: "" });
  const [module, setModule] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZE_OPTIONS[0]);
  const q = useDebouncedValue(search.trim());

  const { data: modules } = useAuditModulesQuery();
  const { data, isFetching, isError, refetch } = useAuditQuery({
    q,
    module,
    date_from: range.from,
    date_to: range.to,
    days: range.from ? undefined : 30,
    page,
    page_size: pageSize,
  });

  const columns = useMemo(() => getActivityColumns(), []);
  const reset = <T,>(set: (v: T) => void) => (v: T) => {
    set(v);
    setPage(1);
  };

  return (
    <Box className="activity-log-page" sx={activityLogStyles}>
      <PageHeader
        title="Activity Log"
        subtitle={range.from ? "Every recorded action in the chosen dates." : "Every recorded action in the last 30 days."}
      />

      <div className="page-body">
        <div className="log-panel">
          <div className="log-toolbar">
            <CustomDateRange value={range} onChange={reset(setRange)} />
            <CustomSelect
              options={(modules?.modules ?? []).map((m) => ({ value: m, label: m }))}
              value={module}
              onChange={reset(setModule)}
              placeholder="All modules"
              ariaLabel="Filter by module"
            />
            <div className="header-search">
              <CustomSearchBox
                ariaLabel="Search by person, action or document"
                placeholder="Search by person, action or document"
                value={search}
                onChange={reset(setSearch)}
              />
            </div>
          </div>

          <div className="log-grid">
            {isError ? (
              <ErrorState message="Could not load the activity log." onRetry={refetch} />
            ) : (
              <CustomAgGrid<AuditEvent>
                rowData={data?.events ?? []}
                columnDefs={columns}
                loading={isFetching && !data}
                emptyText="No activity found"
              />
            )}
          </div>
          <CustomPagination
            dense
            showGoTo
            page={page}
            totalPages={Math.max(1, data?.pagination.total_pages ?? 1)}
            onChange={setPage}
            pageSize={pageSize}
            pageSizeOptions={PAGE_SIZE_OPTIONS}
            onPageSizeChange={reset(setPageSize)}
          />
        </div>
      </div>
    </Box>
  );
};

export default ActivityLog;
