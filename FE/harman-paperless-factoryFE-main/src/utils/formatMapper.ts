import type { FileItem, FolderNode } from "../constants/types";
import type { Format } from "../api/formats.api";

const toFile = (f: Format): FileItem =>
  ({
    id: f.id,
    name: f.title,
    type: f.frequency_label,
    department: f.team?.name ?? "",
    tag: f.code,
    uploadedBy: f.process_owner?.name ?? "",
    description: f.description ?? f.work_instruction_ref ?? "",
    filedDate: f.created_at?.slice(0, 10),
    hasBlank: f.has_blank,
  }) as FileItem;

const splitPath = (path?: string | null) =>
  (path ?? "")
    .split("/")
    .map((p) => p.trim())
    .filter(Boolean);

/**
 * Formats grouped by their template folder (`folder_path`, "A / B"). Folder ids
 * are the path parts joined by ">". `extraPaths` adds folders that hold no
 * format yet (the administrator's empty template folders).
 */
export const formatsToFolders = ({ formats }: { formats: Format[] }, extraPaths: string[] = []): FolderNode[] => {
  const roots: FolderNode[] = [];
  const index = new Map<string, FolderNode>();

  const ensure = (parts: string[]): FolderNode => {
    const id = parts.join(">");
    const existing = index.get(id);
    if (existing) return existing;

    const node = { id, name: parts[parts.length - 1], files: [], children: [] } as FolderNode;
    index.set(id, node);
    if (parts.length === 1) roots.push(node);
    else ensure(parts.slice(0, -1)).children!.push(node);
    return node;
  };

  extraPaths.forEach((path) => {
    const parts = splitPath(path);
    if (parts.length) ensure(parts);
  });
  formats.forEach((f) => {
    const parts = splitPath(f.folder_path);
    ensure(parts.length ? parts : ["Unfiled"]).files!.push(toFile(f));
  });

  return roots;
};

/** A folder id ("Teams>2026") back to the API's folder path ("Teams / 2026"). */
export const folderIdToPath = (id: string | null) => (id ? id.split(">").join(" / ") : null);
