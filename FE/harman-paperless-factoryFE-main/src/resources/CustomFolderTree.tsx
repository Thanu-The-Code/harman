import { forwardRef, useImperativeHandle, useState } from "react";
import { Box, Collapse, Menu, MenuItem } from "@mui/material";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import FolderIcon from "@mui/icons-material/Folder";
import PushPinIcon from "@mui/icons-material/PushPin";
import PushPinOutlinedIcon from "@mui/icons-material/PushPinOutlined";
import CreateNewFolderOutlinedIcon from "@mui/icons-material/CreateNewFolderOutlined";
import DriveFileRenameOutlineIcon from "@mui/icons-material/DriveFileRenameOutline";
import DeleteOutlinedIcon from "@mui/icons-material/DeleteOutlined";
import DragIndicatorOutlinedIcon from "@mui/icons-material/DragIndicatorOutlined";

import { folderMenuPaperSx, folderTreeStyles } from "./style";
import type { FolderNode } from "../constants/types";
import CustomDialog from "../base/dialog/CustomDialog";
import CustomTextField from "../base/dialog/CustomTextField";

// eslint-disable-next-line react-refresh/only-export-components
export const findFolder = (
  nodes: FolderNode[],
  id: string,
): FolderNode | undefined => {
  for (const node of nodes) {
    if (node.id === id) return node;
    const match = node.children && findFolder(node.children, id);
    if (match) return match;
  }
};

const updateFolder = (
  nodes: FolderNode[],
  id: string,
  update: (f: FolderNode) => FolderNode,
): FolderNode[] =>
  nodes.map((n) =>
    n.id === id
      ? update(n)
      : n.children
        ? { ...n, children: updateFolder(n.children, id, update) }
        : n,
  );

const removeFolder = (nodes: FolderNode[], id: string): FolderNode[] =>
  nodes
    .filter((n) => n.id !== id)
    .map((n) =>
      n.children ? { ...n, children: removeFolder(n.children, id) } : n,
    );

const collectIds = (f: FolderNode): string[] => [
  f.id,
  ...(f.children ?? []).flatMap(collectIds),
];

// "a/b/c" -> ["a", "a/b", "a/b/c"]
const ancestorPaths = (path: string) =>
  path.split("/").map((_, i, p) => p.slice(0, i + 1).join("/"));

interface NodesProps {
  nodes: FolderNode[];
  parentPath?: string;
  selectedPath: string;
  expanded: Set<string>;
  pinned: Set<string>;
  onSelect: (node: FolderNode, path: string) => void;
  onContextMenu: (node: FolderNode, path: string, anchor: HTMLElement) => void;
  onToggle: (path: string) => void;
}

const TreeNodes = ({ nodes, parentPath = "", ...rest }: NodesProps) => (
  <>
    {nodes.map((node) => {
      const path = parentPath ? `${parentPath}/${node.id}` : node.id;
      const hasChildren = !!node.children?.length;
      const isOpen = hasChildren && rest.expanded.has(path);

      return (
        <div key={node.id}>
          <div
            className={`tree-row ${rest.selectedPath === path ? "selected" : ""}`}
            role="button"
            tabIndex={0}
            aria-label={`Select ${node.name}`}
            aria-expanded={hasChildren ? isOpen : undefined}
            onClick={() => rest.onSelect(node, path)}
            onContextMenu={(e) => {
              e.preventDefault();
              rest.onContextMenu(node, path, e.currentTarget);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                rest.onSelect(node, path);
              } else if (
                e.key === "ContextMenu" ||
                (e.shiftKey && e.key === "F10")
              ) {
                e.preventDefault();
                rest.onContextMenu(node, path, e.currentTarget);
              }
            }}
          >
            <span
              style={{ display: "flex" }}
              aria-hidden="true"
              onClick={(e) => {
                e.stopPropagation();
                if (hasChildren) rest.onToggle(path);
              }}
            >
              {isOpen ? (
                <ExpandMoreIcon className="tree-chevron" />
              ) : hasChildren ? (
                <ChevronRightIcon className="tree-chevron" />
              ) : (
                <span className="tree-chevron-spacer" />
              )}
            </span>
            <FolderIcon className="tree-folder-icon" />
            <span className="tree-folder-name">{node.name}</span>
            {rest.pinned.has(node.id) && (
              <PushPinIcon className="tree-pin-icon" />
            )}
            {rest.selectedPath === path && (
              <DragIndicatorOutlinedIcon
                className="tree-drag-indicator"
                aria-hidden="true"
              />
            )}
          </div>

          {hasChildren && (
            <Collapse in={isOpen} unmountOnExit>
              <div className="tree-children">
                <TreeNodes nodes={node.children!} parentPath={path} {...rest} />
              </div>
            </Collapse>
          )}
        </div>
      );
    })}
  </>
);

/* create / rename dialog — mounted only while open so the input starts fresh */
const FolderNameDialog = ({
  title,
  confirmText,
  initialName,
  onSave,
  onClose,
}: {
  title: string;
  confirmText: string;
  initialName: string;
  onSave: (name: string) => void;
  onClose: () => void;
}) => {
  const [name, setName] = useState(initialName);
  const submit = () => name.trim() && onSave(name.trim());

  return (
    <CustomDialog
      open
      maxWidth="xs"
      title={title}
      confirmText={confirmText}
      confirmDisabled={!name.trim()}
      onClose={onClose}
      onConfirm={submit}
    >
      <div onKeyDown={(e) => e.key === "Enter" && submit()}>
        <CustomTextField
          label="Folder name"
          placeholder="Enter folder name"
          value={name}
          onChange={setName}
        />
      </div>
    </CustomDialog>
  );
};

export interface CustomFolderTreeHandle {
  /** create a top-level folder (e.g. from a "Create Folder" button) */
  createFolder: () => void;
}

/** Which right-click actions a screen offers; only offer what its API saves. */
export interface FolderActions {
  create?: boolean;
  rename?: boolean;
  pin?: boolean;
  delete?: boolean;
}

const ALL_ACTIONS: FolderActions = { create: true, rename: true, pin: true, delete: true };

interface Props {
  folders: FolderNode[];
  defaultSelectedPath: string;
  onSelect?: (folder: FolderNode | null) => void;
  onCreate?: (parentId: string | null, name: string) => Promise<void>;
  /** Saves a rename; rejecting keeps the dialog open. Without it a rename is local only. */
  onRename?: (folder: FolderNode, name: string) => Promise<void>;
  /** Saves a pin; rejecting puts the pin back. */
  onPin?: (folder: FolderNode, pinned: boolean) => Promise<void>;
  /** Folders pinned on the server. */
  pinnedIds?: string[];
  actions?: FolderActions;
  title?: string;
  className?: string;
}

const CustomFolderTree = forwardRef<CustomFolderTreeHandle, Props>(
  (
    {
      folders,
      defaultSelectedPath,
      onSelect,
      onCreate,
      onRename,
      onPin,
      pinnedIds,
      actions = ALL_ACTIONS,
      title = "Folders",
      className,
    },
    ref,
  ) => {
    const hasMenu = Object.values(actions).some(Boolean);
    const [tree, setTree] = useState(folders);
    const [selectedPath, setSelectedPath] = useState(defaultSelectedPath);
    const [expanded, setExpanded] = useState(
      () => new Set(ancestorPaths(defaultSelectedPath)),
    );
    const [pinned, setPinned] = useState(() => new Set<string>(pinnedIds ?? []));
    const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null);
    const [dialog, setDialog] = useState<{
      action: "create" | "rename";
      folder: FolderNode | null;
      path: string;
    } | null>(null);
    const [toDelete, setToDelete] = useState<{
      folder: FolderNode;
      path: string;
    } | null>(null);

    const selectedFolder =
      findFolder(tree, selectedPath.split("/").pop() ?? "") ?? null;
    const isPinned = !!selectedFolder && pinned.has(selectedFolder.id);

    useImperativeHandle(ref, () => ({
      createFolder: () =>
        setDialog({ action: "create", folder: null, path: "" }),
    }));

    // choosing a folder also opens it: a folder of folders ("Teams") shows nothing of its own
    const select = (folder: FolderNode, path: string) => {
      setSelectedPath(path);
      if (folder.children?.length) setExpanded((cur) => (cur.has(path) ? cur : new Set([...cur, path])));
      onSelect?.(folder);
    };

    const toggle = (path: string) =>
      setExpanded((cur) => {
        const next = new Set(cur);
        if (next.has(path)) next.delete(path);
        else next.add(path);
        return next;
      });

    const closeMenu = () => setMenuAnchor(null);

  const saveFolder = async (name: string) => {
  if (!dialog) return;

  if (dialog.action === "create" && onCreate) {
    try {
      await onCreate(dialog.folder?.id ?? null, name);
    } catch {
      return; // keep the dialog open so the user can retry
    }
    if (dialog.folder) setExpanded((cur) => new Set([...cur, dialog.path]));
    setDialog(null);
    return;
  }

  if (dialog.action === "create") {
    const child: FolderNode = { id: crypto.randomUUID(), name, files: [], children: [] };
    setTree((cur) =>
      dialog.folder
        ? updateFolder(cur, dialog.folder.id, (f) => ({ ...f, children: [...(f.children ?? []), child] }))
        : [...cur, child],
    );
    if (dialog.folder) setExpanded((cur) => new Set([...cur, dialog.path]));
    select(child, dialog.folder ? `${dialog.path}/${child.id}` : child.id);
  } else if (dialog.folder) {
    if (onRename) {
      try {
        await onRename(dialog.folder, name);
      } catch {
        return; // keep the dialog open so the user can retry
      }
    }
    setTree((cur) => updateFolder(cur, dialog.folder!.id, (f) => ({ ...f, name })));
    if (dialog.path === selectedPath) onSelect?.({ ...dialog.folder, name });
  }
  setDialog(null);
};

    const confirmDelete = () => {
      if (!toDelete) return;
      const removed = new Set(collectIds(toDelete.folder));
      const nextTree = removeFolder(tree, toDelete.folder.id);
      setTree(nextTree);
      setPinned((cur) => new Set([...cur].filter((id) => !removed.has(id))));

      if (
        selectedPath === toDelete.path ||
        selectedPath.startsWith(`${toDelete.path}/`)
      ) {
        const parts = toDelete.path.split("/");
        const parentPath = parts.slice(0, -1).join("/");
        const parent = parentPath
          ? findFolder(nextTree, parts[parts.length - 2])
          : nextTree[0];
        setSelectedPath(parentPath || parent?.id || "");
        onSelect?.(parent ?? null);
      }
      setToDelete(null);
    };

    return (
      <Box
        component="aside"
        className={`custom-folder-tree ${className ?? ""}`}
        sx={folderTreeStyles}
      >
        <div className="folder-panel-title">{title}</div>
        <div className="folder-panel-body">
          <TreeNodes
            nodes={tree}
            selectedPath={selectedPath}
            expanded={expanded}
            pinned={pinned}
            onSelect={select}
            onToggle={toggle}
            onContextMenu={(folder, path, anchor) => {
              select(folder, path);
              if (hasMenu) setMenuAnchor(anchor);
            }}
          />
        </div>

        {/* right-click menu */}
        <Menu
          anchorEl={menuAnchor}
          open={Boolean(menuAnchor)}
          onClose={closeMenu}
          anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
          transformOrigin={{ vertical: "top", horizontal: "left" }}
          slotProps={{ paper: { sx: folderMenuPaperSx } }}
        >
          {actions.create && (
          <MenuItem
            onClick={() => {
              closeMenu();
              setDialog({
                action: "create",
                folder: selectedFolder,
                path: selectedPath,
              });
            }}
          >
            <CreateNewFolderOutlinedIcon /> New Folder
          </MenuItem>
          )}
          {actions.rename && (
          <MenuItem
            onClick={() => {
              closeMenu();
              if (selectedFolder)
                setDialog({
                  action: "rename",
                  folder: selectedFolder,
                  path: selectedPath,
                });
            }}
          >
            <DriveFileRenameOutlineIcon /> Rename
          </MenuItem>
          )}
          {actions.pin && (
          <MenuItem
            onClick={() => {
              closeMenu();
              if (!selectedFolder) return;
              const pinning = !pinned.has(selectedFolder.id);
              const toggle = (on: boolean) =>
                setPinned((cur) => {
                  const next = new Set(cur);
                  if (on) next.add(selectedFolder.id);
                  else next.delete(selectedFolder.id);
                  return next;
                });
              toggle(pinning);
              onPin?.(selectedFolder, pinning).catch(() => toggle(!pinning));
            }}
          >
            {isPinned ? <PushPinIcon /> : <PushPinOutlinedIcon />}{" "}
            {isPinned ? "Unpin" : "Pin"}
          </MenuItem>
          )}
          {actions.delete && (
          <MenuItem
            onClick={() => {
              closeMenu();
              if (selectedFolder)
                setToDelete({ folder: selectedFolder, path: selectedPath });
            }}
          >
            <DeleteOutlinedIcon /> Delete
          </MenuItem>
          )}
        </Menu>

        {dialog && (
          <FolderNameDialog
            title={
              dialog.action === "rename" ? "Rename folder" : "Create folder"
            }
            confirmText={dialog.action === "rename" ? "Save" : "Create"}
            initialName={
              dialog.action === "rename" ? (dialog.folder?.name ?? "") : ""
            }
            onSave={saveFolder}
            onClose={() => setDialog(null)}
          />
        )}

        <CustomDialog
          open={Boolean(toDelete)}
          maxWidth="xs"
          title="Delete folder?"
          confirmText="Delete"
          onClose={() => setToDelete(null)}
          onConfirm={confirmDelete}
        >
          <span>
            Delete “{toDelete?.folder.name}” and all of its subfolders? This
            cannot be undone.
          </span>
        </CustomDialog>
      </Box>
    );
  },
);

CustomFolderTree.displayName = "CustomFolderTree";
export default CustomFolderTree;
