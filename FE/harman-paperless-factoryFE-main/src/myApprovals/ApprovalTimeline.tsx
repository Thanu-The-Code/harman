import { Box } from "@mui/material";
import CheckIcon from "@mui/icons-material/Check";
import AccessTimeIcon from "@mui/icons-material/AccessTime";
import Person2OutlinedIcon from '@mui/icons-material/Person2Outlined';
import { approvalTimelineStyles } from "./style";

export type StepStatus = "Completed" | "In Progress" | "Pending" | "Changes requested";

export interface TimelineStep {
  id: string;
  step: number;
  title: string;
  role: string;
  department: string;
  status: StepStatus;
  notes?: string[];
  by: string;
  at?: string; // omitted for steps that haven't happened yet
}

const toClass = (s: StepStatus) => s.toLowerCase().replace(/ /g, "-");

interface Props {
  steps: TimelineStep[];
  className?: string;
}

const ApprovalTimeline = ({ steps, className }: Props) => (
  <Box className={`approval-timeline ${className ?? ""}`} sx={approvalTimelineStyles}>
    {steps.map((s) => {
      const cls = toClass(s.status);
      return (
        <div className={`timeline-item ${cls}`} key={s.id}>
          <span className={`timeline-marker ${cls}`}>
            {s.status === "Completed" ? <CheckIcon /> : <AccessTimeIcon />}
          </span>
          <span className="step-chip">Step {s.step}</span>

          <div className="step-card">
            <div className="step-top">
              <div>
                <div className="step-title">{s.title}</div>
                <div className="step-role">
                  <b>{s.role}</b>{s.department ? ` · ${s.department}` : ""}
                </div>
              </div>
              <span className={`status-chip ${cls}`}>{s.status}</span>
            </div>

            {s.notes && (
              <ul className="step-notes">
                {s.notes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            )}

            <div className="step-meta">
              <span><Person2OutlinedIcon /> {s.by}</span>
              {s.at && <span><AccessTimeIcon /> {s.at}</span>}
            </div>
          </div>
        </div>
      );
    })}
  </Box>
);

export default ApprovalTimeline;