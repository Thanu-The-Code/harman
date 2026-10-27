import { useMemo } from 'react';
import { Box, Chip, IconButton, Link, Paper, Typography } from '@mui/material';
import VisibilityOutlinedIcon from '@mui/icons-material/VisibilityOutlined';
import type { ColDef } from 'ag-grid-community';
import type { ApprovalRow } from './types';
import CustomAgGrid from '../base/aggrid';


interface Props {
  rows: ApprovalRow[];
  onView?: (row: ApprovalRow) => void;
  onViewAll?: () => void;
  /** All waiting items (the table shows the first few). */
  total?: number;
}

export default function ActionRequiredTable({ rows, onView, onViewAll, total }: Props) {
  const columnDefs = useMemo<ColDef<ApprovalRow>[]>(
    () => [
      { headerName: 'Document Name', field: 'documentName', flex: 2, wrapText: true },
      { headerName: 'Current Approval Step', field: 'approvalStep', flex: 1.4 },
      { headerName: 'Due Date', field: 'dueDate', flex: 1 },
      {
        headerName: 'Action',
        width: 90,
        cellStyle: { display: 'flex', justifyContent: 'flex-end' },
        headerClass: 'ag-right-aligned-header',
        cellRenderer: ({ data }: { data?: ApprovalRow }) => (
          <IconButton
            size="small"
            aria-label="View document"
            onClick={(e) => { e.stopPropagation(); if (data) onView?.(data); }}
            sx={{ border: '1px solid #e5e7eb', borderRadius: 1 }}
          >
            <VisibilityOutlinedIcon fontSize="small" />
          </IconButton>
        ),
      },
    ],
    [onView]
  );

  return (
    <Paper variant="outlined" sx={{ p: 2, borderRadius: 2, borderColor: '#e5e7eb' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1.5 }}>
        <Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography sx={{ fontSize: 15, fontWeight: 600 }}>Action Required</Typography>
            <Chip
              label={`${total ?? rows.length} Items`}
              size="small"
              sx={{ bgcolor: '#fef3c7', color: '#b45309', fontSize: 11, height: 20 }}
            />
          </Box>
          <Typography sx={{ fontSize: 12, color: '#6b7280' }}>
            Document waiting for your approval.
          </Typography>
        </Box>
        <Link component="button" underline="none" onClick={onViewAll} sx={{ fontSize: 12, color: '#14b8a6' }}>
          View All
        </Link>
      </Box>
      <CustomAgGrid<ApprovalRow>
        rowData={rows}
        columnDefs={columnDefs}
        gridOptions={{ domLayout: 'autoHeight' }}
      />
    </Paper>
  );
}
