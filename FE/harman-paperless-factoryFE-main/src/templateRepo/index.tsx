import { useMemo, useState } from "react";
import { Box, CircularProgress, IconButton, InputAdornment, TextField } from "@mui/material";
import CalendarTodayOutlinedIcon from "@mui/icons-material/CalendarTodayOutlined";
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import PageHeader from "../base/pageHeader";
import CustomSearchBox from "../base/search/CustomSearch";
import type { FileItem, FolderNode } from "../constants/types";
import CustomFolderTree, { findFolder } from "../resources/CustomFolderTree";
import CustomPagination from "../base/pagination";
import { ErrorState } from "../base/feedback";
import { docRepositoryStyles } from "../docRepository/style";
import TemplateDetail from "./TemplateDetail";
import {
  formatStatusLabel,
  useFormatRepositoryQuery,
  type RepositoryTemplate,
  type TemplateFolder,
} from "../api/formats.api";
import { formatDate } from "../utils/date";

const PAGE_SIZE_OPTIONS = [10, 25, 50];
const UNFILED = "__unfiled__";

const toFile = (t: RepositoryTemplate): FileItem =>
  ({
    id: t.id,
    name: t.title,
    type: t.frequency_label,
    department: t.team?.name ?? "",
    tag: t.code,
    uploadedBy: t.released_version ? `Rev ${t.released_version.revision} released` : "Not released",
    description: formatStatusLabel(t.latest_version.status, t.latest_version.approval_status),
    filedDate: t.latest_version.created_at?.slice(0, 10),
  }) as FileItem;

/** Template folders, each holding its templates; templates outside every folder go under "Unfiled". */
const toTree = (folders: TemplateFolder[], templates: RepositoryTemplate[]): FolderNode[] => {
  const byId = new Map(templates.map((t) => [t.id, t]));
  const placed = new Set<string>();
  const build = (node: TemplateFolder): FolderNode => {
    const files = (node.templates ?? [])
      .map((ref) => byId.get(ref.id))
      .filter((t): t is RepositoryTemplate => !!t)
      .map((t) => {
        placed.add(t.id);
        return toFile(t);
      });
    return { id: node.path, name: node.name, files, children: node.children.map(build) } as FolderNode;
  };
  const tree = folders.map(build);
  const unfiled = templates.filter((t) => !placed.has(t.id)).map(toFile);
  if (unfiled.length) tree.push({ id: UNFILED, name: "Unfiled", files: unfiled, children: [] } as FolderNode);
  return tree;
};

/** Every template and its revisions, by template folder (administrators). */
const TemplateRepo = () => {
  const { data, isLoading, isError, error, refetch } = useFormatRepositoryQuery();
  const folders = useMemo(() => (data ? toTree(data.folders, data.templates) : []), [data]);
  const templatesById = useMemo(() => new Map((data?.templates ?? []).map((t) => [t.id, t])), [data]);

  const [selectedFolderId, setSelectedFolderId] = useState<string | null>(null);
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);
  const [showDetail, setShowDetail] = useState(false);
  const [search, setSearch] = useState("");
  const [filedDate, setFiledDate] = useState("");
  const [pageSize, setPageSize] = useState(PAGE_SIZE_OPTIONS[0]);
  const [page, setPage] = useState(1);

  // the first folder is open until somebody chooses
  const selectedFolder = (selectedFolderId && findFolder(folders, selectedFolderId)) || folders[0] || null;
  const selectedTemplate = selectedFileId ? templatesById.get(selectedFileId) : undefined;

  const handleFolderSelect = (folder: FolderNode | null) => {
    if (folder?.id !== selectedFolder?.id) {
      setSelectedFileId(null);
      setPage(1);
    }
    setSelectedFolderId(folder?.id ?? null);
  };

  const visibleFiles = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (selectedFolder?.files ?? []).filter(
      (f) =>
        (!q || f.name.toLowerCase().includes(q) || f.tag.toLowerCase().includes(q) || f.department.toLowerCase().includes(q)) &&
        (!filedDate || f.filedDate === filedDate),
    );
  }, [selectedFolder, search, filedDate]);

  const totalPages = Math.max(1, Math.ceil(visibleFiles.length / pageSize));
  const pageFiles = visibleFiles.slice((page - 1) * pageSize, page * pageSize);

  if (showDetail && selectedTemplate) {
    return <TemplateDetail template={selectedTemplate} onBack={() => setShowDetail(false)} />;
  }

  return (
    <Box className="doc-repository-page" sx={docRepositoryStyles}>
      <PageHeader
        title="Template Repository"
        subtitle="Every template and its revisions, by template folder"
        actions={
          <div className="header-search">
            <CustomSearchBox
              ariaLabel="Search by code, title or department"
              placeholder="Search by code, title or department"
              value={search}
              onChange={(v) => {
                setSearch(v);
                setPage(1);
              }}
            />
          </div>
        }
      />

      <div className="page-body">
        <div className="repository-layout">
          {isLoading ? (
            <div className="repo-state">
              <CircularProgress size={24} />
            </div>
          ) : isError ? (
            <div className="repo-state">
              <ErrorState message={(error && "message" in error && error.message) || "Could not load templates."} onRetry={refetch} />
            </div>
          ) : folders.length === 0 ? (
            <div className="repo-state">No templates yet.</div>
          ) : (
            <CustomFolderTree
              key={folders.map((f) => f.id).join("|")}
              folders={folders}
              defaultSelectedPath={selectedFolder?.id ?? ""}
              onSelect={handleFolderSelect}
              actions={{}}
            />
          )}

          <section className="documents-panel">
            <div className="documents-heading">
              <div>
                <h2>{selectedFolder?.name ?? "Templates"}</h2>
                <p>Select a template to see its revisions and release history.</p>
              </div>
              <TextField
                className="date-filter"
                type="date"
                size="small"
                value={filedDate}
                onChange={(e) => {
                  setFiledDate(e.target.value);
                  setPage(1);
                }}
                slotProps={{
                  input: {
                    startAdornment: (
                      <InputAdornment position="start">
                        <CalendarTodayOutlinedIcon fontSize="small" />
                      </InputAdornment>
                    ),
                  },
                  htmlInput: { "aria-label": "Filter by created date" },
                }}
              />
            </div>

            <div className="documents-table-wrap">
              <table className="documents-table">
                <thead>
                  <tr>
                    <th>Template</th>
                    <th>Type</th>
                    <th>Release</th>
                    <th>Latest revision</th>
                    <th className="action-column">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {pageFiles.map((file) => (
                    <tr
                      key={file.id}
                      className={selectedFileId === file.id ? "selected" : ""}
                      onClick={() => setSelectedFileId(file.id)}
                    >
                      <td>
                        {file.name}
                        <div style={{ fontSize: 11, color: "#6b7280" }}>
                          {file.tag} · {file.department}
                        </div>
                      </td>
                      <td>{file.type}</td>
                      <td>{file.uploadedBy}</td>
                      <td>
                        {file.description} · {formatDate(file.filedDate)}
                      </td>
                      <td className="action-column">
                        <IconButton
                          className="file-action"
                          aria-label={`Open ${file.name}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedFileId(file.id);
                            setShowDetail(true);
                          }}
                        >
                          <VisibilityOutlinedIcon fontSize="small" />
                        </IconButton>
                      </td>
                    </tr>
                  ))}
                  {pageFiles.length === 0 && (
                    <tr>
                      <td className="empty-table" colSpan={5}>
                        No templates in this folder.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
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
          </section>
        </div>
      </div>
    </Box>
  );
};

export default TemplateRepo;
