import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Box, Button, Menu, MenuItem, Typography } from '@mui/material';
import CalendarTodayOutlinedIcon from '@mui/icons-material/CalendarTodayOutlined';
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import StatCard from './StatCard';
import DocumentActivityChart from './DocumentActivityChart';
import ActionRequiredTable from './ActionRequiredTable';
import RecentActivity from './RecentActivity';
import type { ActivityItem, ActivityPoint, ApprovalRow, StatCardData } from './types';
import { firstName, useMeQuery } from '../api/auth.api';
import { useDashboardQuery } from '../api/dashboard.api';
import { STAGE_STEP, useMyApprovalsQuery } from '../api/approvals.api';
import { useFormatStatsQuery } from '../api/formats.api';
import { useListDcrQuery, useListRcrQuery } from '../api/changeRequests.api';
import { useAuditQuery } from '../api/audit.api';
import { formatDateTime, formatRelative } from '../utils/date';

const RANGES = [7, 30, 90];

const pct = (n?: number) => (n === undefined ? '' : `${n > 0 ? '+' : ''}${Math.round(n)}%`);

const ACTIVITY_TYPE: Record<string, ActivityItem['type']> = {
  'Template Builder': 'template',
  'People & Teams': 'person',
  'Doc Repository': 'resource',
  'My Documents': 'record',
  'Change Request': 'approval',
};

/** The workspace at a glance: records, approvals waiting, change requests, templates, activity. */
export default function DashboardPage() {
  const navigate = useNavigate();
  const [days, setDays] = useState(7);
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);

  const { data: me } = useMeQuery();
  const { data: dash } = useDashboardQuery({ days });
  const { data: approvals } = useMyApprovalsQuery({ tab: 'pending', per_page: 5 });
  const { data: templates } = useFormatStatsQuery();
  const { data: dcr } = useListDcrQuery({});
  const { data: rcr } = useListRcrQuery({ status: 'open', page_size: 1 });
  const { data: audit } = useAuditQuery({ page_size: 5, days, work_only: true });

  // the charts redraw whenever their data changes identity, so it is rebuilt only with the dashboard data
  const openSpark = useMemo(() => (dash?.trend ?? []).map((b) => b.open), [dash]);
  const activity = useMemo<ActivityPoint[]>(
    () =>
      (dash?.trend ?? []).map((b) => ({
        date: b.label,
        passed: b.passed,
        failed: b.failed,
        open: b.open,
        completed: b.completed,
      })),
    [dash],
  );
  const openDcr = (dcr?.stats.submitted ?? 0) + (dcr?.stats.under_review ?? 0);
  const waitingCr = (dcr?.waiting_on_me ?? 0) + (rcr?.waiting_on_me ?? 0);

  const stats: StatCardData[] = [
    {
      title: 'Inspection Records',
      value: dash?.totals.total ?? 0,
      caption: dash
        ? `${dash.totals.completed} filed · ${dash.totals.pass_rate === null ? 'nothing judged yet' : `${dash.totals.pass_rate}% within spec`}`
        : 'Loading…',
      trend: pct(dash?.totals.growth.total),
      color: '#14b8a6',
      spark: [],
      size: 'large',
    },
    {
      title: 'Pending Approvals',
      value: approvals?.counts.pending ?? 0,
      caption: `${approvals?.counts.overdue ?? 0} overdue`,
      trend: '',
      color: '#ef4444',
      spark: openSpark,
    },
    {
      title: 'Open Change Requests',
      value: openDcr + (rcr?.stats.open ?? 0),
      caption: `${waitingCr} waiting on you`,
      trend: '',
      color: '#f59e0b',
      spark: [],
    },
    {
      title: 'Active Templates',
      value: templates?.published ?? 0,
      caption: `${(templates?.draft ?? 0) + (templates?.on_verification ?? 0)} in the builder`,
      trend: '',
      color: '#3b82f6',
      spark: [],
    },
  ];

  const rows: ApprovalRow[] = (approvals?.items ?? []).map((i) => ({
    id: i.record_id,
    documentName: i.document_name,
    approvalStep: STAGE_STEP[i.stage] ?? i.stage,
    dueDate: formatDateTime(i.due_at),
  }));

  const recent: ActivityItem[] = (audit?.events ?? []).map((e) => ({
    id: e.id,
    title: `${e.label}${e.user ? ` · ${e.user}` : ''}`,
    time: formatRelative(e.at),
    type: ACTIVITY_TYPE[e.module] ?? 'record',
  }));

  const RangeButton = (
    <>
      <Button
        variant="outlined"
        size="small"
        startIcon={<CalendarTodayOutlinedIcon sx={{ fontSize: 14 }} />}
        endIcon={<KeyboardArrowDownIcon />}
        onClick={(e) => setAnchor(e.currentTarget)}
        sx={{ color: '#374151', borderColor: '#e5e7eb', textTransform: 'none', fontSize: 12 }}
      >
        Last {days} days
      </Button>
      <Menu anchorEl={anchor} open={!!anchor} onClose={() => setAnchor(null)}>
        {RANGES.map((d) => (
          <MenuItem
            key={d}
            selected={d === days}
            onClick={() => {
              setDays(d);
              setAnchor(null);
            }}
          >
            Last {d} days
          </MenuItem>
        ))}
      </Menu>
    </>
  );

  return (
    <Box sx={{ p: 2.5, bgcolor: '#f3f9f9', minHeight: '100%' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2 }}>
        <Box>
          <Typography sx={{ fontSize: 22, fontWeight: 700 }}>
            Hi, <Box component="span" sx={{ color: '#14b8a6' }}>{firstName(me)}</Box>
          </Typography>
          <Typography sx={{ fontSize: 12, color: '#6b7280' }}>
            Here&apos;s an overview of your workspace and pending actions.
          </Typography>
        </Box>
        {RangeButton}
      </Box>

      {/* KPI row */}
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: '1.1fr 1fr 1fr 1fr' }, mb: 2 }}>
        {stats.map((s) => (
          <StatCard key={s.title} {...s} />
        ))}
      </Box>

      {/* Main + sidebar */}
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', lg: '1fr 260px' }, alignItems: 'start' }}>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
          <DocumentActivityChart data={activity} filter={RangeButton} />
          <ActionRequiredTable
            rows={rows}
            total={approvals?.counts.pending}
            onView={(r) => navigate(`/my-approvals/${r.id}`)}
            onViewAll={() => navigate('/my-approvals')}
          />
        </Box>
        <RecentActivity items={recent} onViewAll={() => navigate('/activity-log')} />
      </Box>
    </Box>
  );
}
