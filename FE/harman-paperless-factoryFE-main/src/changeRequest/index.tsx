import { useMemo, useState } from "react";
import { Box, Button, FormControlLabel, Switch } from "@mui/material";
import { useNavigate, useSearchParams } from "react-router-dom";
import PageHeader from "../base/pageHeader";
import StatsSummary from "../base/stats/StatsSummary";
import CustomTabs, { type TabOption } from "../base/tabs/CustomTabs";
import CustomSelect from "../base/dropdown/CustomSelect";
import CustomSearchBox from "../base/search/CustomSearch";
import CustomAgGrid from "../base/aggrid";
import CustomPagination from "../base/pagination";
import { ErrorState } from "../base/feedback";
import { ConstantLogo } from "../assets";
import { changeRequestStyles } from "./style";
import { getDcrColumns, getRcrColumns } from "./Columns";
import RaiseDcrDialog from "./RaiseDcrDialog";
import { useListDcrQuery, useListRcrQuery, type Dcr, type DcrStatus, type Rcr, type RcrStatus } from "../api/changeRequests.api";
import { useFormatTeamsQuery } from "../api/formats.api";
import { useDebouncedValue } from "../hooks/useDebouncedValue";

type Mode = "dcr" | "rcr";

const MODES: TabOption<Mode>[] = [
  { value: "dcr", label: "Format changes (DCR)" },
  { value: "rcr", label: "Record changes" },
];

const DCR_TABS: TabOption<DcrStatus>[] = [
  { value: "submitted", label: "Submitted" },
  { value: "under_review", label: "Under review" },
  { value: "approved", label: "Approved" },
  // carried out: the next revision (or the new format) is drafted, then released through review
  { value: "implemented", label: "Executed" },
  { value: "rejected", label: "Not approved" },
];

const RCR_TABS: TabOption<RcrStatus>[] = [
  { value: "open", label: "Open" },
  { value: "approved", label: "Approved" },
  { value: "implemented", label: "Implemented" },
  { value: "not_approved", label: "Not approved" },
];

const PAGE_SIZE = 10;

/**
 * Change requests: changes to a released format (DCR, approved by the QMS
 * Coordinator before execution) and changes asked for on a filled record.
 */
const ChangeRequestDash = () => {
  const { total_doc, change_doc, draft_doc, verification_doc } = ConstantLogo;
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const mode: Mode = params.get("type") === "rcr" ? "rcr" : "dcr";
  const [dcrTab, setDcrTab] = useState<DcrStatus>("submitted");
  const [rcrTab, setRcrTab] = useState<RcrStatus>("open");
  const [search, setSearch] = useState("");
  const [teamId, setTeamId] = useState("");
  const [waiting, setWaiting] = useState(false);
  const [page, setPage] = useState(1);
  const [raising, setRaising] = useState(false);
  const q = useDebouncedValue(search.trim());

  const { data: teams } = useFormatTeamsQuery();
  const dcr = useListDcrQuery({ status: dcrTab, team_id: teamId, waiting: waiting || undefined }, { skip: mode !== "dcr" });
  const dcrStats = useListDcrQuery({ team_id: teamId }, { skip: mode !== "dcr" });
  const teamName = teams?.teams.find((t) => t.id === teamId)?.name;
  const rcr = useListRcrQuery(
    { status: rcrTab, search: q, department: teamName, waiting: waiting || undefined, page, page_size: PAGE_SIZE },
    { skip: mode !== "rcr" },
  );

  const dcrRows = useMemo(() => {
    const term = q.toLowerCase();
    return (dcr.data?.requests ?? []).filter(
      (r) =>
        !term ||
        r.title.toLowerCase().includes(term) ||
        r.number.toLowerCase().includes(term) ||
        (r.format?.code ?? "").toLowerCase().includes(term),
    );
  }, [dcr.data, q]);

  const dcrColumns = useMemo(() => getDcrColumns({ onView: (r: Dcr) => navigate(`/change-request/dcr/${r.id}`) }), [navigate]);
  const rcrColumns = useMemo(() => getRcrColumns({ onView: (r: Rcr) => navigate(`/change-request/rcr/${r.id}`) }), [navigate]);

  const s = dcrStats.data?.stats;
  const r = rcr.data?.stats;
  const items =
    mode === "dcr"
      ? [
          { label: "Submitted", value: s?.submitted ?? 0, icon: total_doc, onClick: () => setDcrTab("submitted") },
          { label: "Under review", value: s?.under_review ?? 0, icon: verification_doc, onClick: () => setDcrTab("under_review") },
          { label: "Approved", value: s?.approved ?? 0, icon: change_doc, onClick: () => setDcrTab("approved") },
          { label: "Executed", value: s?.implemented ?? 0, icon: draft_doc, onClick: () => setDcrTab("implemented") },
        ]
      : [
          { label: "Open", value: r?.open ?? 0, icon: total_doc, onClick: () => setRcrTab("open") },
          { label: "Approved", value: r?.approved ?? 0, icon: verification_doc, onClick: () => setRcrTab("approved") },
          { label: "Implemented", value: r?.implemented ?? 0, icon: change_doc, onClick: () => setRcrTab("implemented") },
          { label: "Not approved", value: r?.not_approved ?? 0, icon: draft_doc, onClick: () => setRcrTab("not_approved") },
        ];

  const waitingCount = mode === "dcr" ? dcr.data?.waiting_on_me : rcr.data?.waiting_on_me;
  const active = mode === "dcr" ? dcr : rcr;

  const reset = <T,>(set: (v: T) => void) => (v: T) => {
    set(v);
    setPage(1);
  };

  return (
    <Box className="change-request-page" sx={changeRequestStyles}>
      <PageHeader
        title="Change Request"
        subtitle="Changes to released formats (approved by the QMS Coordinator) and to filled records."
        actions={
          mode === "dcr" && (
            <Button variant="contained" onClick={() => setRaising(true)} sx={{ textTransform: "none", bgcolor: "#14b8a6" }}>
              New change request
            </Button>
          )
        }
      />

      <div className="page-body">
        <CustomTabs tabs={MODES} value={mode} onChange={(m) => setParams(m === "rcr" ? { type: "rcr" } : {}, { replace: true })} />
        <StatsSummary items={items} />

        <div className="change-panel">
          <div className="change-toolbar">
            {mode === "dcr" ? (
              <CustomTabs tabs={DCR_TABS} value={dcrTab} onChange={reset(setDcrTab)} />
            ) : (
              <CustomTabs tabs={RCR_TABS} value={rcrTab} onChange={reset(setRcrTab)} />
            )}

            <div className="toolbar-actions">
              <FormControlLabel
                control={<Switch size="small" checked={waiting} onChange={(e) => reset(setWaiting)(e.target.checked)} />}
                label={`Waiting on me${waitingCount ? ` (${waitingCount})` : ""}`}
                sx={{ "& .MuiFormControlLabel-label": { fontSize: 13 } }}
              />
              <CustomSelect
                options={(teams?.teams ?? []).map((t) => ({ value: t.id, label: t.name }))}
                value={teamId}
                onChange={reset(setTeamId)}
                placeholder="Select Team"
                ariaLabel="Filter by team"
              />
              <div className="header-search">
                <CustomSearchBox
                  ariaLabel="Find a change request"
                  placeholder="Find by title, number or code"
                  value={search}
                  onChange={reset(setSearch)}
                />
              </div>
            </div>
          </div>

          <div className="change-grid">
            {active.isError ? (
              <ErrorState message="Could not load change requests." onRetry={active.refetch} />
            ) : mode === "dcr" ? (
              <CustomAgGrid<Dcr>
                rowData={dcrRows}
                columnDefs={dcrColumns}
                loading={dcr.isFetching && !dcr.data}
                emptyText="No change requests here"
              />
            ) : (
              <CustomAgGrid<Rcr>
                rowData={rcr.data?.requests ?? []}
                columnDefs={rcrColumns}
                loading={rcr.isFetching && !rcr.data}
                emptyText="No record change requests here"
              />
            )}
          </div>
          {mode === "rcr" && (
            <CustomPagination page={page} totalPages={Math.max(1, rcr.data?.pages ?? 1)} onChange={setPage} />
          )}
        </div>
      </div>

      {raising && <RaiseDcrDialog open onClose={() => setRaising(false)} />}
    </Box>
  );
};

export default ChangeRequestDash;
