import React, { useMemo, useRef, useState } from "react";
import { Box, Button, CircularProgress, Dialog, IconButton, Tooltip } from "@mui/material";
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import CloseIcon from "@mui/icons-material/Close";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import DownloadOutlinedIcon from "@mui/icons-material/DownloadOutlined";
import FullscreenOutlinedIcon from "@mui/icons-material/FullscreenOutlined";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "react-toastify";

import type { FolderNode } from "../constants/types";
import { resourcesStyles } from "./style";
import CustomSearchBox from "../base/search/CustomSearch";
import CustomFolderTree, { findFolder, type CustomFolderTreeHandle } from "./CustomFolderTree";
import CustomDialog from "../base/dialog/CustomDialog";
import { ErrorState } from "../base/feedback";
import RaiseDcrDialog from "../changeRequest/RaiseDcrDialog";
import { folderIdToPath, formatsToFolders } from "../utils/formatMapper";
import { useMeQuery } from "../api/auth.api";
import {
  useCallableFormatsQuery,
  useCreateTemplateFolderMutation,
  useListFormatsQuery,
  useTemplateFoldersQuery,
  type CallableFormat,
  type TemplateFolder,
} from "../api/formats.api";
import { useCallFormatMutation } from "../api/records.api";
import { getApiErrorMessage } from "../api/errors";
import { useAuthedObjectUrl } from "../hooks/useAuthedObjectUrl";

const PAGE_SIZE = 15;

const flattenPaths = (nodes: TemplateFolder[] = []): string[] =>
  nodes.flatMap((n) => [n.path, ...flattenPaths(n.children)]);

/**
 * The released blank formats, by template folder (process step 1). The
 * Process Owner calls a format from here to fill a record (step 2).
 */
const Resources: React.FC = () => {
  const treeRef = useRef<CustomFolderTreeHandle>(null);
  const navigate = useNavigate();

  const { data: me } = useMeQuery();
  const isAdmin = !!me?.is_admin;
  const { data, isLoading, isError, error, refetch } = useListFormatsQuery({ status: "active" });
  const { data: folderData } = useTemplateFoldersQuery(undefined, { skip: !isAdmin });
  const { data: callableData } = useCallableFormatsQuery();
  const [createFolder] = useCreateTemplateFolderMutation();
  const [callFormat, { isLoading: calling }] = useCallFormatMutation();

  const folders = useMemo(
    () => (data ? formatsToFolders(data, isAdmin ? flattenPaths(folderData?.folders) : []) : []),
    [data, folderData, isAdmin],
  );
  const formatsById = useMemo(() => new Map((data?.formats ?? []).map((f) => [f.id, f])), [data]);
  const callableById = useMemo(
    () => new Map((callableData?.formats ?? []).map((f) => [f.id, f])),
    [callableData],
  );

  // `?format=<id>` (a notification about a period still to be filled) opens that format
  const [params] = useSearchParams();
  const requested = params.get("format");
  const requestedFolder = useMemo(() => {
    const walk = (nodes: FolderNode[]): FolderNode | null => {
      for (const n of nodes) {
        if (n.files?.some((f) => f.id === requested)) return n;
        const hit = n.children ? walk(n.children) : null;
        if (hit) return hit;
      }
      return null;
    };
    return requested ? walk(folders) : null;
  }, [folders, requested]);
  const [selectedFolderId, setSelectedFolderId] = useState<string | null>(null);
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);
  const [isPreviewZoomed, setIsPreviewZoomed] = useState(false);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [dcrOpen, setDcrOpen] = useState(false);
  const [existing, setExisting] = useState<CallableFormat | null>(null);

  // the first folder (and its first file) is open until somebody chooses
  const selectedFolder: FolderNode | null =
    (selectedFolderId && findFolder(folders, selectedFolderId)) || requestedFolder || folders[0] || null;
  const folderFiles = useMemo(() => selectedFolder?.files ?? [], [selectedFolder]);
  // a search looks through every folder, not just the open one
  const query = search.trim().toLowerCase();
  const files = useMemo(() => {
    if (!query) return folderFiles;
    const all: typeof folderFiles = [];
    const walk = (nodes: FolderNode[]) =>
      nodes.forEach((n) => {
        all.push(...(n.files ?? []));
        if (n.children) walk(n.children);
      });
    walk(folders);
    return all.filter(
      (f, i) =>
        all.findIndex((x) => x.id === f.id) === i &&
        (f.name.toLowerCase().includes(query) || f.tag.toLowerCase().includes(query) || f.department.toLowerCase().includes(query)),
    );
  }, [folderFiles, folders, query]);
  const selectedFile =
    selectedFileId === "none" ? null : files.find((f) => f.id === (selectedFileId ?? requested)) ?? files[0] ?? null;
  const selectedFormat = selectedFile ? formatsById.get(selectedFile.id) : undefined;
  const callable = selectedFile ? callableById.get(selectedFile.id) : undefined;

  const blank = useAuthedObjectUrl(selectedFormat?.has_blank ? `api/formats/${selectedFormat.id}/blank?inline=true` : null);
  const previewSource = blank.url;
  const isImagePreview = !!blank.mimeType?.startsWith("image/");

  // fired by the folder tree on click
  const handleFolderSelect = (folder: FolderNode | null) => {
    if (folder?.id !== selectedFolder?.id) {
      setSelectedFileId(null);
      setPage(1);
    }
    setSelectedFolderId(folder?.id ?? null);
  };

  const handleCreateFolder = async (parentId: string | null, name: string) => {
    try {
      await createFolder({ name, parent_path: folderIdToPath(parentId) }).unwrap();
      toast.success(`Folder "${name}" created`);
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Could not create the folder"));
      throw err; // tells the tree to keep the dialog open
    }
  };

  const startRecord = async (formatId: string) => {
    try {
      const record = await callFormat({ format_id: formatId }).unwrap();
      toast.success(`${record.number} raised for ${record.period_label}.`);
      navigate(`/my-forms/${record.id}`);
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Could not open the form for filling."));
    }
  };

  const handleFile = () => {
    if (!callable) return;
    const current = callable.existing_for_period;
    if (current?.stage === "filling") {
      navigate(`/my-forms/${current.id}`); // resume the draft for this period
    } else if (current) {
      setExisting(callable); // already submitted for this period: ask first
    } else {
      startRecord(callable.id);
    }
  };

  const totalPages = Math.max(1, Math.ceil(files.length / PAGE_SIZE));
  const pageFiles = files.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const renderPreviewDocument = (className: string) => {
    if (blank.loading) {
      return (
        <div className="preview-unavailable">
          <CircularProgress size={20} />
        </div>
      );
    }
    if (!previewSource) {
      return (
        <div className="preview-unavailable">
          <VisibilityOutlinedIcon />
          <span>
            {selectedFormat?.has_blank
              ? blank.error ?? "Preview is not available for this file."
              : "No blank form is attached. The form is filled on screen."}
          </span>
        </div>
      );
    }

    return isImagePreview ? (
      <img className={className} src={previewSource} alt={`Preview of ${selectedFile?.name ?? "selected file"}`} />
    ) : (
      <iframe className={className} title={selectedFile?.name ?? "Document preview"} src={previewSource} />
    );
  };

  if (isError) {
    return (
      <Box className="resources-page" sx={resourcesStyles}>
        <ErrorState message={(error && "message" in error && error.message) || "Could not load the library."} onRetry={refetch} />
      </Box>
    );
  }

  return (
    <Box className="resources-page" sx={resourcesStyles}>
      <div className="page-header">
        <div>
          <h1 className="page-title">Resources</h1>
          <p className="page-subtitle">Released formats, ready to be filled. Choose one and select File.</p>
        </div>
        <div className="header-actions">
          <CustomSearchBox
            ariaLabel="Find a template by title"
            placeholder="Find a template by title or code"
            value={search}
            onChange={(value) => {
              setSearch(value);
              setPage(1);
            }}
          />
          {isAdmin && (
            <Button className="primary-btn" variant="contained" onClick={() => treeRef.current?.createFolder()}>
              Create Folder
            </Button>
          )}
        </div>
      </div>

      <div className="layout">
        {/* Folders – same component as the Document Repository */}
        {isLoading ? (
          <div className="panel">
            <div className="empty-state">
              <CircularProgress size={24} />
            </div>
          </div>
        ) : (
          <CustomFolderTree
            // re-read the tree whenever the server's folders change
            key={folders.map((f) => f.id).join("|") + (folderData?.folders.length ?? 0)}
            ref={treeRef}
            folders={folders}
            defaultSelectedPath={selectedFolder?.id ?? ""}
            onSelect={handleFolderSelect}
            onCreate={handleCreateFolder}
            actions={{ create: isAdmin }}
          />
        )}

        {/* File list */}
        <div className="panel">
          <div className="panel-title">{query ? `Search: “${search.trim()}”` : selectedFolder?.name ?? "Folders"}</div>
          <div className="panel-caption">
            {query
              ? `${files.length} released ${files.length === 1 ? "format matches" : "formats match"} in every folder.`
              : `${folderFiles.length} released ${folderFiles.length === 1 ? "format" : "formats"} in this folder.`}
          </div>
          <div className="panel-body">
            {pageFiles.length === 0 ? (
              <div className="empty-state">{isLoading ? "Loading…" : query ? "No released format matches." : "No files in this folder."}</div>
            ) : (
              <table className="file-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Type</th>
                    <th className="col-action">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {pageFiles.map((file) => (
                    <tr
                      key={file.id}
                      className={`file-row ${selectedFile?.id === file.id ? "selected" : ""}`}
                      onClick={() => setSelectedFileId(file.id)}
                    >
                      <td>
                        {file.name}
                        <div style={{ fontSize: 11, color: "#6b7280" }}>{file.tag}</div>
                      </td>
                      <td>{file.type}</td>
                      <td className="col-action">
                        <IconButton
                          className="eye-btn"
                          size="small"
                          aria-label={`Preview ${file.name}`}
                          onClick={(e) => {
                            e.stopPropagation(); // don't also select the row
                            setSelectedFileId(file.id);
                            setIsPreviewZoomed(Boolean(formatsById.get(file.id)?.has_blank));
                          }}
                        >
                          <VisibilityOutlinedIcon fontSize="small" />
                        </IconButton>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          <div className="pagination">
            <IconButton className="page-btn" disabled={page === 1} onClick={() => setPage(page - 1)}>
              <ChevronLeftIcon fontSize="small" />
            </IconButton>
            {Array.from({ length: totalPages }, (_, i) => (
              <IconButton
                key={i}
                className={`page-btn ${page === i + 1 ? "active" : ""}`}
                onClick={() => setPage(i + 1)}
                sx={{ fontSize: 12 }}
              >
                {i + 1}
              </IconButton>
            ))}
            <IconButton className="page-btn" disabled={page === totalPages} onClick={() => setPage(page + 1)}>
              <ChevronRightIcon fontSize="small" />
            </IconButton>
          </div>
        </div>

        {/* Preview */}
        <div className="panel">
          {selectedFile && selectedFormat ? (
            <>
              <div className="preview-header">
                <div className="preview-title">{selectedFile.name}</div>
                <IconButton
                  className="close-btn"
                  size="small"
                  aria-label="Close preview"
                  onClick={() => {
                    setSelectedFileId("none");
                    setIsPreviewZoomed(false);
                  }}
                >
                  <CloseIcon fontSize="small" />
                </IconButton>
              </div>
              <div className="preview-body">
                <div className="preview-frame">
                  <div className="preview-document">{renderPreviewDocument("preview-content")}</div>
                  <div className="preview-controls">
                    <IconButton
                      className="preview-control-btn"
                      component={previewSource ? "a" : "button"}
                      href={previewSource || undefined}
                      download={previewSource ? (blank.fileName ?? selectedFile.name) : undefined}
                      disabled={!previewSource}
                      aria-label={previewSource ? `Download ${selectedFile.name}` : "Download unavailable"}
                      title={previewSource ? "Download" : "No blank form attached"}
                    >
                      <DownloadOutlinedIcon fontSize="small" />
                    </IconButton>
                    <IconButton
                      className="preview-control-btn"
                      aria-label="Zoom preview"
                      title="Zoom preview"
                      disabled={!previewSource}
                      onClick={() => setIsPreviewZoomed(true)}
                    >
                      <FullscreenOutlinedIcon fontSize="small" />
                    </IconButton>
                  </div>
                </div>
                {[
                  ["Title", selectedFile.name],
                  ["Code", `${selectedFile.tag} · rev ${selectedFormat.revision}`],
                  ["Department", selectedFile.department],
                  ["Frequency", selectedFile.type],
                  ["Process owner", selectedFile.uploadedBy || "Chosen at submission"],
                  ["Work instruction", selectedFormat.work_instruction_ref ?? "—"],
                  ["This period", callable?.period.label ?? "—"],
                  ["Description", selectedFile.description || "—"],
                ].map(([label, value]) => (
                  <div className="detail-row" key={label}>
                    <span className="detail-label">{label}</span>
                    <span className="detail-value">{value}</span>
                  </div>
                ))}
              </div>
              <div className="preview-footer">
                <Button className="link-btn" onClick={() => setDcrOpen(true)}>
                  Change Request
                </Button>
                <Tooltip
                  title={callable ? `Fill the record for ${callable.period.label}` : "Only this format's Process Owner may fill it"}
                  arrow
                >
                  <span>
                    <Button className="primary-btn" variant="contained" disabled={!callable || calling} onClick={handleFile}>
                      {calling ? "Opening…" : "File"}
                    </Button>
                  </span>
                </Tooltip>
              </div>
            </>
          ) : (
            <div className="empty-state">Select a file to preview it.</div>
          )}
        </div>
      </div>

      <Dialog
        className="preview-zoom-dialog"
        open={isPreviewZoomed && Boolean(previewSource)}
        onClose={() => setIsPreviewZoomed(false)}
        fullScreen
        sx={{
          "& .MuiDialog-paper": {
            display: "flex",
            flexDirection: "column",
            background: "#f8fafc",
          },
          "& .preview-zoom-header": {
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "16px",
            padding: "12px 20px",
            borderBottom: "1px solid #e5e7eb",
            background: "#fff",
          },
          "& .preview-zoom-content": {
            flex: 1,
            minHeight: 0,
            padding: "20px",
            display: "flex",
            justifyContent: "center",
          },
          "& .preview-zoom-document": {
            display: "block",
            width: "100%",
            height: "100%",
            border: 0,
            background: "#fff",
            objectFit: "contain",
            boxShadow: "0 2px 8px rgba(15, 23, 42, 0.12)",
          },
        }}
      >
        <div className="preview-zoom-header">
          <div className="preview-title">{selectedFile?.name}</div>
          <IconButton className="close-btn" aria-label="Close zoomed preview" onClick={() => setIsPreviewZoomed(false)}>
            <CloseIcon />
          </IconButton>
        </div>
        <div className="preview-zoom-content">{renderPreviewDocument("preview-zoom-document")}</div>
      </Dialog>

      {selectedFormat && dcrOpen && (
        <RaiseDcrDialog open format={selectedFormat} onClose={() => setDcrOpen(false)} />
      )}

      <CustomDialog
        open={Boolean(existing)}
        onClose={() => setExisting(null)}
        onConfirm={() => {
          const id = existing?.existing_for_period?.id;
          setExisting(null);
          if (id) navigate(`/my-forms/${id}`);
        }}
        title="A record already exists for this period"
        subtitle={
          existing && (
            <>
              {existing.existing_for_period?.number} for {existing.period.label} is already submitted. Open it, or start
              another record (for example a repeat check).
            </>
          )
        }
        confirmText="Open existing"
        cancelText="Cancel"
      >
        <Button
          variant="outlined"
          onClick={() => {
            const id = existing?.id;
            setExisting(null);
            if (id) startRecord(id);
          }}
          sx={{ textTransform: "none" }}
        >
          Start a new record instead
        </Button>
      </CustomDialog>
    </Box>
  );
};

export default Resources;
