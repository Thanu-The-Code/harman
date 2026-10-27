import React, { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Box } from "@mui/material";
import CustomAgGrid from "../base/aggrid";
import CustomSearchBox from "../base/search/CustomSearch";
import CustomSelect from "../base/dropdown/CustomSelect";
import CustomTabs, { type TabOption } from "../base/tabs/CustomTabs";
import { getApprovalColumns } from "./Columns";
import { myApprovalsStyles } from "./style";
import CustomPagination from "../base/pagination";
import { ConstantLogo } from "../assets";
import StatsSummary from "../base/stats/StatsSummary";
import { ErrorState } from "../base/feedback";
import TemplateApprovals from "./TemplateApprovals";
import { useMyFormatApprovalsQuery } from "../api/formats.api";
import {
  useMyApprovalDepartmentsQuery,
  useMyApprovalsQuery,
  useTaskStatsQuery,
  type MyApprovalItem,
  type MyApprovalsTab,
} from "../api/approvals.api";
import { useDebouncedValue } from "../hooks/useDebouncedValue";

const PAGE_SIZE = 10;

type Tab = MyApprovalsTab | "templates";

const TAB_LABELS: Record<Tab, string> = {
  overdue: "Overdue",
  pending: "Pending Approval",
  returned: "Returned",
  templates: "Template approvals",
};

interface Props {
  embedded?: boolean;
}

/** Records waiting on the signed-in person, plus template release reviews. */
const MyApprovalsDash: React.FC<Props> = ({ embedded = false }) => {
  const { total_doc, change_doc, draft_doc, verification_doc } = ConstantLogo;
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("pending");
  const [search, setSearch] = useState("");
  const [department, setDepartment] = useState("");
  const [page, setPage] = useState(1);
  const q = useDebouncedValue(search.trim());

  const { data: stats } = useTaskStatsQuery();
  const { data: departments = [] } = useMyApprovalDepartmentsQuery();
  const { data: templateReviews } = useMyFormatApprovalsQuery();
  const { data, isFetching, isError, error, refetch } = useMyApprovalsQuery(
    { tab: tab === "templates" ? "pending" : tab, search: q, department, page, per_page: PAGE_SIZE },
    { skip: tab === "templates" },
  );

  const counts = data?.counts;
  const tabs: TabOption<Tab>[] = (Object.keys(TAB_LABELS) as Tab[]).map((value) => {
    const count = value === "templates" ? templateReviews?.count : counts?.[value];
    return { value, label: count ? `${TAB_LABELS[value]} (${count})` : TAB_LABELS[value] };
  });

  const items = [
    { label: "Pending", value: stats?.pending ?? 0, icon: total_doc, onClick: () => setTab("pending") },
    { label: "Overdue", value: stats?.overdue ?? 0, icon: verification_doc, onClick: () => setTab("overdue") },
    { label: "Returned", value: stats?.returned ?? 0, icon: change_doc, onClick: () => setTab("returned") },
    { label: "Approved today", value: stats?.approved_today ?? 0, icon: draft_doc },
  ];

  const columns = useMemo(
    () =>
      getApprovalColumns({
        // a returned record is corrected on its fill page; everything else is reviewed
        onView: (row: MyApprovalItem) =>
          navigate(row.stage === "filling" ? `/my-forms/${row.record_id}` : `/my-approvals/${row.record_id}`),
        overdue: tab === "overdue",
      }),
    [navigate, tab],
  );

  const reset = <T,>(set: (v: T) => void) => (v: T) => {
    set(v);
    setPage(1);
  };

  return (
    <Box className={`my-approvals-page${embedded ? " approvals-embedded" : ""}`} sx={myApprovalsStyles}>
      {!embedded && <StatsSummary items={items} />}
      <div className="approvals-panel">
        <div className="approvals-toolbar">
          <CustomTabs tabs={tabs} value={tab} onChange={reset(setTab)} />

          <div className="toolbar-actions">
            <div className="header-search">
              <CustomSearchBox
                ariaLabel="Find a document by name"
                placeholder="Find a document by name"
                value={search}
                onChange={reset(setSearch)}
              />
            </div>
            {tab !== "templates" && (
              <CustomSelect
                options={departments.map((d) => ({ value: d, label: d }))}
                value={department}
                onChange={reset(setDepartment)}
                placeholder="Select Department"
                ariaLabel="Filter by department"
              />
            )}
          </div>
        </div>

        <div className="approvals-grid">
          {tab === "templates" ? (
            <TemplateApprovals search={search} />
          ) : isError ? (
            <ErrorState message={(error && "message" in error && error.message) || "Could not load your approvals."} onRetry={refetch} />
          ) : (
            <CustomAgGrid<MyApprovalItem>
              rowData={data?.items ?? []}
              columnDefs={columns}
              loading={isFetching && !data}
              emptyText={tab === "returned" ? "Nothing has been returned to you" : "Nothing is waiting for you"}
            />
          )}
        </div>

        {tab !== "templates" && (
          <CustomPagination page={page} totalPages={Math.max(1, data?.total_pages ?? 1)} onChange={setPage} />
        )}
      </div>
    </Box>
  );
};

export default MyApprovalsDash;
