import React, { useMemo, useState } from "react";
import { Box, MenuItem, Select, Tab, Tabs } from "@mui/material";
import { useNavigate } from "react-router-dom";
import { templatesStyles } from "./style";
import { type MainDocumentTabs, type TemplateTab } from "../constants/types";
import CustomSearchBox from "../base/search/CustomSearch";
import CustomAgGrid from "../base/aggrid";
import { getColumns } from "../base/aggrid/Column";
import PageHeader from "../base/pageHeader";
import CustomPagination from "../base/pagination";
import { ErrorState } from "../base/feedback";
import MyApprovalsDash from "../myApprovals";
import { useDocumentsListingQuery, type DocumentListItem } from "../api/records.api";
import { useDebouncedValue } from "../hooks/useDebouncedValue";

const PAGE_SIZE_OPTIONS = [10, 25, 50];

/** My Documents: records I fill or am involved in (On Verification) and my drafts. */
const MyFormsDash: React.FC = () => {
  const navigate = useNavigate();
  const [mainTab, setMainTab] = useState<MainDocumentTabs>("documents");
  const [tab, setTab] = useState<TemplateTab>("verification");
  const [search, setSearch] = useState("");
  const [department, setDepartment] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZE_OPTIONS[0]);
  const q = useDebouncedValue(search.trim());

  const { data, isFetching, isError, error, refetch } = useDocumentsListingQuery(
    { tab, q, team_id: department, page, page_size: pageSize },
    { skip: mainTab !== "documents" },
  );

  const columns = useMemo(
    () =>
      getColumns({
        onTrack: (row: DocumentListItem) => navigate(`/my-forms/${row.id}?tab=track`),
        onView: (row: DocumentListItem) => navigate(`/my-forms/${row.id}`),
      }),
    [navigate],
  );

  const resetPage = <T,>(set: (v: T) => void) => (v: T) => {
    set(v);
    setPage(1);
  };

  return (
    <Box className="templates-page" sx={templatesStyles}>
      <PageHeader title="My Documents" subtitle="Records you fill, their reporting periods, and their approvals." />
      <div className="main-document-tabs">
        <Tabs
          className="templates-tabs"
          value={mainTab}
          onChange={(_, value: MainDocumentTabs) => setMainTab(value)}
          aria-label="My document sections"
        >
          <Tab className="templates-tab" value="documents" label="Documents" />
          <Tab className="templates-tab" value="approvals" label="Approvals" />
        </Tabs>
      </div>

      {mainTab === "approvals" ? (
        <MyApprovalsDash embedded />
      ) : (
        <div className="templates-panel">
          <div className="templates-toolbar">
            <Tabs
              className="templates-tabs"
              value={tab}
              onChange={(_, value: TemplateTab) => resetPage(setTab)(value)}
              aria-label="Document status"
            >
              <Tab
                className="templates-tab"
                value="verification"
                label={`On Verification${data ? ` (${data.counts.verification})` : ""}`}
              />
              <Tab className="templates-tab" value="draft" label={`Draft${data ? ` (${data.counts.draft})` : ""}`} />
            </Tabs>

            <div className="toolbar-actions">
              <div className="header-search">
                <CustomSearchBox
                  ariaLabel="Find a record by title or number"
                  placeholder="Find by title or record number"
                  value={search}
                  onChange={resetPage(setSearch)}
                />
              </div>
              <Select
                className="status-select"
                size="small"
                displayEmpty
                value={department}
                onChange={(event) => resetPage(setDepartment)(event.target.value)}
                renderValue={(value) => data?.departments.find((d) => d.id === value)?.name || "Department"}
                inputProps={{ "aria-label": "Filter by department" }}
              >
                <MenuItem value="">All Departments</MenuItem>
                {(data?.departments ?? []).map((option) => (
                  <MenuItem key={option.id} value={option.id}>
                    {option.name}
                  </MenuItem>
                ))}
              </Select>
            </div>
          </div>

          <div className="templates-grid">
            {isError ? (
              <ErrorState message={(error && "message" in error && error.message) || "Could not load your documents."} onRetry={refetch} />
            ) : (
              <CustomAgGrid<DocumentListItem>
                rowData={data?.items ?? []}
                columnDefs={columns}
                loading={isFetching && !data}
                emptyText={tab === "draft" ? "No records being filled" : "No records awaiting verification"}
                gridOptions={{ onRowDoubleClicked: (e) => e.data && navigate(`/my-forms/${e.data.id}`) }}
              />
            )}
          </div>

          <CustomPagination
            dense
            page={page}
            totalPages={Math.max(1, data?.total_pages ?? 1)}
            onChange={setPage}
            pageSize={pageSize}
            pageSizeOptions={PAGE_SIZE_OPTIONS}
            onPageSizeChange={resetPage(setPageSize)}
          />
        </div>
      )}
    </Box>
  );
};

export default MyFormsDash;
