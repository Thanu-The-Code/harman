import { useMemo, useState } from "react";
import { Box, CircularProgress, IconButton, InputAdornment, TextField } from "@mui/material";
import CalendarTodayOutlinedIcon from "@mui/icons-material/CalendarTodayOutlined";
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import { toast } from "react-toastify";
import PageHeader from "../base/pageHeader";
import CustomSearchBox from "../base/search/CustomSearch";
import type { FolderNode } from "../constants/types";
import CustomFolderTree from "../resources/CustomFolderTree";
import { docRepositoryStyles } from "./style";
import CustomPagination from "../base/pagination";
import { ErrorState } from "../base/feedback";
import RecordFileDetail from "./RecordFileDetail";
import { useMeQuery } from "../api/auth.api";
import {
  idToPath,
  pathToId,
  usePinRepositoryFolderMutation,
  useRenameRepositoryFolderMutation,
  useRepositoryQuery,
  type RepositoryFolder,
} from "../api/repository.api";
import { getApiErrorMessage } from "../api/errors";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import { formatDate } from "../utils/date";

const PAGE_SIZE_OPTIONS = [10, 25, 50];
const ALL = "__all__";

const toNodes = (folders: RepositoryFolder[]): FolderNode[] =>
  folders.map((f) => ({
    id: pathToId(f.path),
    name: `${f.name} (${f.total_records})`,
    files: [],
    children: toNodes(f.children),
  }));

const pinnedIds = (folders: RepositoryFolder[]): string[] =>
  folders.flatMap((f) => [...(f.is_pinned ? [pathToId(f.path)] : []), ...pinnedIds(f.children)]);

/**
 * Filed quality records, in the date- and month-wise folders the process
 * builds from each format's frequency (process step 10).
 */
const DocRepository = () => {
  const { data: me } = useMeQuery();
  const [folderId, setFolderId] = useState<string>(ALL);
  const [search, setSearch] = useState("");
  const [filedDate, setFiledDate] = useState("");
  const [pageSize, setPageSize] = useState(PAGE_SIZE_OPTIONS[0]);
  const [page, setPage] = useState(1);
  const [openRecord, setOpenRecord] = useState<string | null>(null);
  const q = useDebouncedValue(search.trim());

  const { data, isFetching, isError, error, refetch } = useRepositoryQuery({
    search: q,
    folder_path: folderId === ALL ? undefined : idToPath(folderId),
    filed_date: filedDate,
    page,
    page_size: pageSize,
  });
  const [renameFolder] = useRenameRepositoryFolderMutation();
  const [pinFolder] = usePinRepositoryFolderMutation();

  // the tree keeps the same shape whatever the filters, so build it from the unfiltered folders
  const { data: tree } = useRepositoryQuery({ page: 1, page_size: 1 });
  const folders = useMemo<FolderNode[]>(
    () => [{ id: ALL, name: "All filed records", files: [], children: toNodes(tree?.folders ?? []) }],
    [tree],
  );
  const pins = useMemo(() => pinnedIds(tree?.folders ?? []), [tree]);

  const reset = <T,>(set: (v: T) => void) => (v: T) => {
    set(v);
    setPage(1);
  };

  if (openRecord) return <RecordFileDetail recordId={openRecord} onBack={() => setOpenRecord(null)} />;

  const selectedName = folderId === ALL ? "All filed records" : idToPath(folderId).split(" / ").pop();

  return (
    <Box className="doc-repository-page" sx={docRepositoryStyles}>
      <PageHeader
        title="Document Repository"
        subtitle="Approved quality records, filed by team, format and date"
        actions={
          <div className="header-search">
            <CustomSearchBox
              ariaLabel="Search by record number, form or department"
              placeholder="Search by record number, form or department"
              value={search}
              onChange={reset(setSearch)}
            />
          </div>
        }
      />

      <div className="page-body">
        <div className="repository-layout">
          {!tree ? (
            <div className="repo-state">
              <CircularProgress size={24} />
            </div>
          ) : (
            <CustomFolderTree
              key={folders[0].children?.map((f) => f.id).join("|")}
              folders={folders}
              defaultSelectedPath={ALL}
              onSelect={(folder) => reset(setFolderId)(folder?.id ?? ALL)}
              pinnedIds={pins}
              actions={{ pin: true, rename: !!me?.is_admin }}
              onPin={async (folder, pinned) => {
                if (folder.id === ALL) return;
                try {
                  await pinFolder({ folder_path: idToPath(folder.id), pinned }).unwrap();
                } catch (err) {
                  toast.error(getApiErrorMessage(err, "Could not pin the folder."));
                  throw err;
                }
              }}
              onRename={async (folder, name) => {
                try {
                  const res = await renameFolder({ folder_path: idToPath(folder.id), new_name: name }).unwrap();
                  toast.success(`Renamed to ${res.new_path}`);
                } catch (err) {
                  toast.error(getApiErrorMessage(err, "Could not rename the folder."));
                  throw err;
                }
              }}
            />
          )}

          <section className="documents-panel">
            <div className="documents-heading">
              <div>
                <h2>{selectedName}</h2>
                <p>
                  {data ? `${data.pagination.total} filed record${data.pagination.total === 1 ? "" : "s"}` : "Loading…"}
                  {folderId !== ALL && ` in ${idToPath(folderId)}`}
                </p>
              </div>
              <TextField
                className="date-filter"
                type="date"
                size="small"
                value={filedDate}
                onChange={(e) => reset(setFiledDate)(e.target.value)}
                slotProps={{
                  input: {
                    startAdornment: (
                      <InputAdornment position="start">
                        <CalendarTodayOutlinedIcon fontSize="small" />
                      </InputAdornment>
                    ),
                  },
                  htmlInput: { "aria-label": "Filter by filed date" },
                }}
              />
            </div>

            <div className="documents-table-wrap">
              {isError ? (
                <ErrorState message={(error && "message" in error && error.message) || "Could not load the repository."} onRetry={refetch} />
              ) : (
                <table className="documents-table">
                  <thead>
                    <tr>
                      <th>Record</th>
                      <th>Type</th>
                      <th>Department</th>
                      <th>Filed by</th>
                      <th>Filed date</th>
                      <th className="action-column">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data?.documents ?? []).map((doc) => (
                      <tr key={doc.record_id} onDoubleClick={() => setOpenRecord(doc.record_id)}>
                        <td className="record-cell">
                          {doc.document_name}
                          <div style={{ fontSize: 11, color: "#6b7280" }}>
                            {doc.document_number} · {doc.period}
                          </div>
                        </td>
                        <td>{doc.type}</td>
                        <td>{doc.department ?? "—"}</td>
                        <td>{doc.filed_by_name ?? "—"}</td>
                        <td>{formatDate(doc.filed_date)}</td>
                        <td className="action-column">
                          <IconButton className="file-action" aria-label={`Open ${doc.document_number}`} onClick={() => setOpenRecord(doc.record_id)}>
                            <VisibilityOutlinedIcon fontSize="small" />
                          </IconButton>
                        </td>
                      </tr>
                    ))}
                    {!isFetching && data?.documents.length === 0 && (
                      <tr>
                        <td className="empty-table" colSpan={6}>
                          No filed records here.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
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
          </section>
        </div>
      </div>
    </Box>
  );
};

export default DocRepository;
