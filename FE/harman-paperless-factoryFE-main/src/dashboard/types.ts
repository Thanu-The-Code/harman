export interface StatCardData {
  title: string;
  value: string | number;
  caption: string;
  trend: string;
  trendUp?: boolean;
  color: string;
  spark: number[];
  size?: "large" | "small";
}

/** One period of inspections (from the dashboard's trend buckets). */
export interface ActivityPoint {
  date: string;
  passed: number;
  failed: number;
  open: number;
  completed: number;
}

export interface ApprovalRow {
  id: string;
  documentName: string;
  approvalStep: string;
  dueDate: string;
}

export interface ActivityItem {
  id: string;
  title: string;
  time: string;
  type: "template" | "team" | "person" | "resource" | "record" | "approval";
}
