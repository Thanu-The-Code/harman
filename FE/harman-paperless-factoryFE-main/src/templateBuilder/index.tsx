import { useMemo, useState } from "react";
import { Box, Button } from "@mui/material";
import { useNavigate } from "react-router-dom";
import StatsSummary from "../base/stats/StatsSummary";
import CustomTabs, { type TabOption } from "../base/tabs/CustomTabs";
import CustomSearchBox from "../base/search/CustomSearch";
import CustomAgGrid from "../base/aggrid";
import { resourcesStyles } from "../resources/style";
import { ConstantLogo } from "../assets";
import { builderStyles } from "./style";
import type { BuilderRow, BuilderTab } from "../constants/types";
import { getBuilderColumns } from "./Column";
import CustomPagination from "../base/pagination";
import { ErrorState } from "../base/feedback";
import { formatStatusLabel, useListFormatsQuery, type BuilderStatus } from "../api/formats.api";
import { formatDate } from "../utils/date";
import UploadDocumentDialog from "./designer/UploadDocumentDialog";

const TABS: TabOption<BuilderTab>[] = [
  { value: "verification", label: "Pending Approval" },
  // sent back by a reviewer (not the Change Request module's DCRs)
  { value: "change-request", label: "Changes Requested" },
  { value: "draft", label: "Draft" },
];

// UI tab -> the API's builder status
const TAB_STATUS: Record<BuilderTab, BuilderStatus> = {
  verification: "on_verification",
  "change-request": "change_request",
  draft: "draft",
};

const PAGE_SIZE_OPTIONS = [10, 25, 50];

const BuilderDash = () => {
  const navigate = useNavigate();
  const { total_doc, change_doc, draft_doc, verification_doc } = ConstantLogo;

  const [tab, setTab] = useState<BuilderTab>("verification");
  const [search, setSearch] = useState("");
  const [pageSize, setPageSize] = useState(PAGE_SIZE_OPTIONS[0]);
  const [page, setPage] = useState(1);
  const [uploading, setUploading] = useState(false);

  // one call returns every unreleased template plus the counts for the tiles
  const { data, isFetching, isError, error, refetch } = useListFormatsQuery({ tab: "all" });
  const summary = data?.summary;

  const items = [
    // work in progress: released templates are in the Template Repo
    { label: "In the Builder", value: summary?.total_document ?? 0, icon: total_doc },
    { label: "Pending Approval", value: summary?.on_verification ?? 0, icon: verification_doc, onClick: () => setTab("verification") },
    { label: "Changes Requested", value: summary?.change_request ?? 0, icon: change_doc, onClick: () => setTab("change-request") },
    { label: "Draft", value: summary?.draft ?? 0, icon: draft_doc, onClick: () => setTab("draft") },
  ];

  const rows = useMemo<BuilderRow[]>(
    () =>
      (data?.formats ?? [])
        .filter((f) => f.builder_status === TAB_STATUS[tab])
        .map((f) => ({
          id: f.id,
          tab,
          code: f.code,
          name: f.title,
          department: f.team?.name ?? "—",
          type: f.frequency_label,
          status: formatStatusLabel(f.status, f.approval_status),
          lastUpdate: formatDate(f.updated_at ?? f.created_at),
        })),
    [data, tab],
  );

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return q
      ? rows.filter(
          (r) =>
            r.name.toLowerCase().includes(q) ||
            r.code?.toLowerCase().includes(q) ||
            r.department.toLowerCase().includes(q),
        )
      : rows;
  }, [rows, search]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const pageRows = filtered.slice((page - 1) * pageSize, page * pageSize);

  const columns = useMemo(
    () => getBuilderColumns({ onView: (row: BuilderRow) => navigate(`/builder/${row.id}`) }),
    [navigate],
  );

  return (
    <Box className="resources-page" sx={resourcesStyles}>
      <div className="page-header">
        <div>
          <h1 className="page-title">Template Builder</h1>
          <p className="page-subtitle">
            Create and manage reusable templates for consistent document creation.
          </p>
        </div>
        <div className="header-actions">
          {/* an Excel workbook, PDF or picture of a form, read into an editable template */}
          <Button className="sec-btn" variant="contained" onClick={() => setUploading(true)}>
            Upload File
          </Button>
          <Button className="primary-btn" variant="contained" onClick={() => navigate("/builder/new/build")}>
            New Template
          </Button>
        </div>
      </div>

      <Box className="builder-body" sx={builderStyles}>
        <StatsSummary items={items} />

        <div className="builder-panel">
          <div className="builder-toolbar">
            <CustomTabs
              tabs={TABS}
              value={tab}
              onChange={(value) => {
                setTab(value);
                setPage(1);
              }}
            />
            <div className="header-search">
              <CustomSearchBox
                ariaLabel="Find a template by title"
                placeholder="Find a template by title or code"
                value={search}
                onChange={(value) => {
                  setSearch(value);
                  setPage(1);
                }}
              />
            </div>
          </div>

          <div className="builder-grid">
            {isError ? (
              <ErrorState message={(error && "message" in error && error.message) || "Could not load templates."} onRetry={refetch} />
            ) : (
              <CustomAgGrid<BuilderRow>
                rowData={pageRows}
                columnDefs={columns}
                loading={isFetching && !data}
                emptyText="No templates found"
                gridOptions={{
                  // click a row to select it; the first row is selected whenever the page changes
                  rowSelection: { mode: "singleRow", checkboxes: false, enableClickSelection: true },
                  onRowDataUpdated: (e) => e.api.getDisplayedRowAtIndex(0)?.setSelected(true),
                  onRowDoubleClicked: (e) => e.data && navigate(`/builder/${e.data.id}`),
                }}
              />
            )}
          </div>

          <CustomPagination
            dense
            showGoTo
            page={page}
            totalPages={totalPages}
            onChange={setPage}
            pageSize={pageSize}
            pageSizeOptions={PAGE_SIZE_OPTIONS}
            onPageSizeChange={(size) => {
              setPageSize(size);
              setPage(1);
            }}
          />
        </div>
      </Box>
      <UploadDocumentDialog open={uploading} onClose={() => setUploading(false)} />
    </Box>
  );
};

export default BuilderDash;
