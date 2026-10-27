import { useMemo, useState } from "react";
import { Button, Dialog, IconButton, InputAdornment, MenuItem, TextField } from "@mui/material";
import SearchIcon from "@mui/icons-material/Search";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import FolderIcon from "@mui/icons-material/Folder";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import CreateNewFolderOutlinedIcon from "@mui/icons-material/CreateNewFolderOutlined";
import { toast } from "react-toastify";
import {
  useCreateTemplateFolderMutation,
  useNextFormatCodeQuery,
  type QualityTeam,
  type TemplateFolder,
} from "../../api/formats.api";
import { getApiErrorMessage } from "../../api/errors";

/**
 * Create Template (Figma: Document create, "Edit"): the form's details and the folder of
 * the Resources library it is published into. The folder is also where approved records
 * of it are filed.
 */

export interface TemplateDetails {
  title: string;
  code: string;
  description: string;
  teamId: string;
  folder: string; // "Quality / Procedures"; "" = Records / <team> / <code>
}

interface Props {
  open: boolean;
  mode: "create" | "edit";
  initial: TemplateDetails;
  teams: QualityTeam[];
  folders: TemplateFolder[];
  onClose: () => void;
  onSubmit: (details: TemplateDetails) => void;
  busy?: boolean;
}

const segments = (path: string) => path.split("/").map((p) => p.trim()).filter(Boolean);

const FolderNode = ({
  node,
  depth,
  selected,
  onSelect,
  query,
  expanded,
  toggle,
}: {
  node: TemplateFolder;
  depth: number;
  selected: string;
  onSelect: (path: string) => void;
  query: string;
  expanded: Set<string>;
  toggle: (path: string) => void;
}) => {
  const matches = (n: TemplateFolder): boolean =>
    !query || n.name.toLowerCase().includes(query) || n.children.some(matches);
  if (!matches(node)) return null;
  const open = !!query || expanded.has(node.path);
  const active = selected === node.path;
  return (
    <li>
      <div
        className={`folder-row${active ? " active" : ""}`}
        style={{ paddingLeft: 8 + depth * 18 }}
        role="treeitem"
        aria-selected={active}
        aria-expanded={node.children.length ? open : undefined}
        onClick={() => onSelect(node.path)}
      >
        <IconButton
          size="small"
          className="folder-toggle"
          aria-label={open ? `Collapse ${node.name}` : `Expand ${node.name}`}
          style={{ visibility: node.children.length ? "visible" : "hidden" }}
          onClick={(e) => {
            e.stopPropagation();
            toggle(node.path);
          }}
        >
          {open ? <ExpandMoreIcon fontSize="small" /> : <ChevronRightIcon fontSize="small" />}
        </IconButton>
        <FolderIcon className="folder-icon" fontSize="small" />
        <span className="folder-name">{node.name}</span>
        {active && <CheckCircleIcon className="folder-check" fontSize="small" />}
      </div>
      {open && node.children.length > 0 && (
        <ul>
          {node.children.map((c) => (
            <FolderNode key={c.path} node={c} depth={depth + 1} {...{ selected, onSelect, query, expanded, toggle }} />
          ))}
        </ul>
      )}
    </li>
  );
};

const TemplateDetailsDialog = ({ open, mode, initial, teams, folders, onClose, onSubmit, busy }: Props) => {
  const [form, setForm] = useState<TemplateDetails>(initial);
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(segments(initial.folder).map((_, i, all) => all.slice(0, i + 1).join(" / "))));
  const [newFolder, setNewFolder] = useState<string | null>(null);
  const [createFolder, { isLoading: creating }] = useCreateTemplateFolderMutation();

  const team = teams.find((t) => t.id === form.teamId);
  // what the server gives a template of this team whose code is left blank
  const { data: next } = useNextFormatCodeQuery(form.teamId, { skip: !form.teamId || mode !== "create" });
  const suggested = next?.code ?? "";
  const set = (patch: Partial<TemplateDetails>) => setForm((f) => ({ ...f, ...patch }));
  const toggle = (path: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });

  const shownPath = useMemo(
    () => (form.folder ? segments(form.folder).join(" / ") : `Records / ${team?.name ?? "<team>"} / ${form.code || suggested || "<code>"}`),
    [form.folder, form.code, team, suggested],
  );

  const addFolder = async () => {
    const name = (newFolder ?? "").trim();
    if (!name) return;
    try {
      const created = await createFolder({ name, parent_path: form.folder || null }).unwrap();
      set({ folder: created.path });
      if (form.folder) setExpanded((prev) => new Set(prev).add(form.folder));
      setNewFolder(null);
      toast.success(`Folder "${name}" created.`);
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Could not create the folder."));
    }
  };

  const valid = form.title.trim() && form.teamId;

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md" className="template-details-dialog">
      <div className="tdd">
        <div className="tdd-head">
          <h2>{mode === "create" ? "Create Template" : "Template details"}</h2>
          <p>Set form details and choose a folder location in resource Library.</p>
        </div>
        <div className="tdd-body">
          <div className="tdd-folders">
            <TextField
              size="small"
              fullWidth
              placeholder="Find a folder by name"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              slotProps={{
                htmlInput: { "aria-label": "Find a folder" },
                input: { startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> },
              }}
            />
            <ul className="folder-tree" role="tree" aria-label="Folders">
              {folders.map((f) => (
                <FolderNode key={f.path} node={f} depth={0} selected={form.folder} onSelect={(path) => set({ folder: path })} query={query.trim().toLowerCase()} expanded={expanded} toggle={toggle} />
              ))}
              {folders.length === 0 && <li className="folder-empty">No folders yet. Add one, or leave it to file records by team and code.</li>}
            </ul>
            {newFolder === null ? (
              <Button size="small" startIcon={<CreateNewFolderOutlinedIcon fontSize="small" />} className="tdd-new-folder" onClick={() => setNewFolder("")}>
                New folder{form.folder ? " here" : ""}
              </Button>
            ) : (
              <div className="tdd-new-folder-row">
                <TextField
                  size="small"
                  autoFocus
                  placeholder="Folder name"
                  value={newFolder}
                  onChange={(e) => setNewFolder(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && addFolder()}
                  slotProps={{ htmlInput: { "aria-label": "New folder name" } }}
                />
                <Button size="small" variant="contained" disabled={creating || !newFolder.trim()} onClick={addFolder}>
                  Add
                </Button>
                <Button size="small" onClick={() => setNewFolder(null)}>
                  Cancel
                </Button>
              </div>
            )}
          </div>

          <div className="tdd-form">
            <div className="tdd-label">Folder Path</div>
            <div className="tdd-path" aria-label="Folder path">
              <FolderIcon className="folder-icon" fontSize="small" />
              <span>{shownPath}</span>
              {form.folder && (
                <button type="button" className="tdd-clear" onClick={() => set({ folder: "" })}>
                  Clear
                </button>
              )}
            </div>
            <div className="tdd-row">
              <div>
                <div className="tdd-label">
                  Form Title<span className="fp-required"> *</span>
                </div>
                <TextField size="small" fullWidth placeholder="Daily initial flow management control items" value={form.title} onChange={(e) => set({ title: e.target.value })} slotProps={{ htmlInput: { "aria-label": "Form title" } }} />
              </div>
              <div>
                <div className="tdd-label">Form Code</div>
                <TextField size="small" fullWidth placeholder={suggested || "Enter code"} value={form.code} onChange={(e) => set({ code: e.target.value.toUpperCase() })} slotProps={{ htmlInput: { "aria-label": "Form code" } }} />
              </div>
            </div>
            <div className="tdd-label">
              Quality Team<span className="fp-required"> *</span>
            </div>
            <TextField select size="small" fullWidth value={teams.some((t) => t.id === form.teamId) ? form.teamId : ""} onChange={(e) => set({ teamId: e.target.value })} slotProps={{ htmlInput: { "aria-label": "Quality team" }, select: { displayEmpty: true } }}>
              <MenuItem value="">
                <em>Select quality team</em>
              </MenuItem>
              {teams.map((t) => (
                <MenuItem key={t.id} value={t.id}>
                  {t.code} - {t.name}
                </MenuItem>
              ))}
            </TextField>
            <div className="tdd-label">Description</div>
            <TextField size="small" fullWidth multiline minRows={4} placeholder="What this form is for" value={form.description} onChange={(e) => set({ description: e.target.value })} slotProps={{ htmlInput: { "aria-label": "Description" } }} />
          </div>
        </div>
        <div className="tdd-foot">
          <Button className="tdd-cancel" onClick={onClose}>
            Cancel
          </Button>
          <Button
            className="tdd-submit"
            variant="contained"
            disabled={!valid || busy}
            onClick={() => onSubmit({ ...form, title: form.title.trim(), code: form.code.trim().toUpperCase() })}
          >
            {busy ? "Saving…" : mode === "create" ? "Create" : "Save"}
          </Button>
        </div>
      </div>
    </Dialog>
  );
};

export default TemplateDetailsDialog;
