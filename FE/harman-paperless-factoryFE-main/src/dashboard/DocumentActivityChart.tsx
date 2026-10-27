import { useMemo } from 'react';
import { Box, Paper, Typography } from '@mui/material';
import Chart from './Chart';
import type { AgCartesianChartOptions } from 'ag-charts-community';
import type { ActivityPoint } from './types';

const SERIES = [
  { yKey: 'passed', yName: 'OK', fill: '#14b8a6' },
  { yKey: 'failed', yName: 'N-OK', fill: '#ef4444' },
  // records with no reading to judge (a request form, a sheet not filled yet) - not their approval stage
  { yKey: 'open', yName: 'Nothing to judge', fill: '#f59e0b' },
  { yKey: 'completed', yName: 'Filed', fill: '#0f8f86' },
] as const;

interface Props {
  data: ActivityPoint[];
  filter?: React.ReactNode; 
}

export default function DocumentActivityChart({ data, filter }: Props) {
  const chartOptions = useMemo<AgCartesianChartOptions>(
    () => ({
      data,
      background: { visible: false },
      padding: { top: 8, right: 8, bottom: 0, left: 0 },
      legend: {
        position: "top",
        item: { marker: { shape: "circle", size: 8 } },
      },
      series: SERIES.map((s) => ({
        type: "bar" as const,
        xKey: "date",
        yKey: s.yKey,
        yName: s.yName,
        fill: s.fill,
        cornerRadius: 3,
        // gap between bars in a group / between groups
        grouped: true,
      })),

      axes: {
        x: {
          type: "category",
          position: "bottom",
          line: { enabled: false },
          tick: { enabled: false },
          paddingInner: 0.35,
          groupPaddingInner: 0.1,
        },
        y: {
          type: "number",
          position: "left",
          min: 0,
          line: { enabled: false },
          gridLine: {
            style: [{ stroke: "#eef0f3", lineDash: [] }],
          },
        },
      },
    }),
    [data],
  );

  return (
    <Paper variant="outlined" sx={{ p: 2, borderRadius: 2, borderColor: '#e5e7eb' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <Box>
          <Typography sx={{ fontSize: 15, fontWeight: 600 }}>Document Activity</Typography>
          <Typography sx={{ fontSize: 12, color: '#6b7280' }}>
            Inspection records by result, over the selected period.
          </Typography>
        </Box>
        {filter}
      </Box>
      <Box sx={{ height: 280, mt: 1 }}>
        <Chart options={chartOptions} style={{ height: '100%' }} />
      </Box>
    </Paper>
  );
}
