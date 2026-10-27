/* View models shared by several screens. API shapes live in src/api/*.api.ts. */

/** A file shown in a folder tree (a released format, a template). */
export interface FileItem {
  id: string;
  name: string;
  type: string; // the frequency label, e.g. "Daily"
  department: string;
  tag: string;
  uploadedBy: string;
  description: string;
  previewUrl?: string;
  filedDate?: string;
  hasBlank?: boolean;
}

export interface FolderNode {
  id: string;
  name: string;
  children?: FolderNode[]; // sub folders
  files?: FileItem[]; // files live inside (sub) folders
}

export type MainDocumentTabs = "documents" | "approvals";
export type TemplateTab = "verification" | "draft";

/** A quality team card. */
export interface Team {
  id: string;
  code: string; // two-letter badge, e.g. "CQ"
  name: string;
  members: number;
  memberInitials: string[];
}

export type BuilderTab = "verification" | "change-request" | "draft";

export interface BuilderRow {
  id: string;
  tab: BuilderTab;
  code?: string;
  status?: string;
  name: string;
  department: string;
  type: string;
  lastUpdate: string;
}
