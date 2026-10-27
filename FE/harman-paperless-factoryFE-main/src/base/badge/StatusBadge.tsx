import { BadgeText, BadgeTooltip, BadgeWrapper } from "./style";

export type StatusType =
  | "pending"
  | "approved"
  | "rejected"
  | "draft"
  | "active"
  | "inactive"
  | "verification"
  | "completed";

type StatusBadgeProps = {
  status: StatusType | string;
  label?: string;
  tooltip?: string;
  className?: string;
};


const getStatusLabel = (status: string) => {
  switch (status.toLowerCase()) {
    case "pending":
      return "Pending";
    case "approved":
      return "Approved";
    case "rejected":
      return "Rejected";
    case "draft":
      return "Draft";
    case "active":
      return "Active";
    case "inactive":
      return "Inactive";
    case "verification":
      return "On Verification";
    case "completed":
      return "Completed";
    default:
      return status;
  }
};

const StatusBadge = ({
  status,
  label,
  tooltip,
  className,
}: StatusBadgeProps) => {
  const normalizedStatus = status.toLowerCase();
  const text = label || getStatusLabel(normalizedStatus);

  return (
    <BadgeWrapper className={className}>
      <BadgeText $status={normalizedStatus}>{text}</BadgeText>

      {tooltip ? (
        <BadgeTooltip className="status-tooltip">{tooltip}</BadgeTooltip>
      ) : null}
    </BadgeWrapper>
  );
};

export default StatusBadge;
