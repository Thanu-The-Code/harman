import { useMemo } from 'react';
import { Box } from '@mui/material';
import {
  AllCommunityModule,
  ModuleRegistry,
  themeQuartz,
  type ColDef,
  type GridOptions,
  type RowClickedEvent,
} from 'ag-grid-community';
import { AgGridReact } from 'ag-grid-react';
import { customAgGridStyles } from './style';

ModuleRegistry.registerModules([AllCommunityModule]);

const gridTheme = themeQuartz.withParams({
  fontFamily: '"Plus Jakarta Sans", "Inter", Roboto, sans-serif',
  fontSize: 13,
  foregroundColor: '#1f2937',
  headerBackgroundColor: '#f7f8fa',
  headerTextColor: '#1f2937',
  headerFontSize: 13,
  borderColor: '#e5e7eb',
  wrapperBorder: false,
  columnBorder: false,
  headerColumnBorder: false,
  headerColumnResizeHandleColor: 'transparent',
  cellHorizontalPadding: 12,
  accentColor: '#14b8a6',
  rowHoverColor: '#f9fafb',
});

export interface CustomAgGridProps<T> {
  rowData: T[];
  columnDefs: ColDef<T>[];
  loading?: boolean;
  quickFilterText?: string;
  emptyText?: string;
  pagination?: boolean;
  pageSize?: number;
  onRowClicked?: (row: T) => void;
  gridOptions?: GridOptions<T>;
  className?: string;
}

function CustomAgGrid<T>({
  rowData,
  columnDefs,
  loading = false,
  quickFilterText,
  emptyText = 'No records found',
  pagination = false,
  pageSize = 10,
  onRowClicked,
  gridOptions,
  className,
}: CustomAgGridProps<T>) {
  const defaultColDef = useMemo<ColDef<T>>(
    () => ({
      sortable: false,
      resizable: false,
      suppressMovable: true,
      wrapText: false,
      autoHeight: true,
    }),
    []
  );

  return (
    <Box className={`custom-ag-grid ${className ?? ''}`} sx={customAgGridStyles}>
      <AgGridReact<T>
        theme={gridTheme}
        rowData={rowData}
        columnDefs={columnDefs}
        defaultColDef={defaultColDef}
        loading={loading}
        quickFilterText={quickFilterText}
        pagination={pagination}
        paginationPageSize={pageSize}
        // the chosen size must be one of the choices, or the page-size box shows blank
        paginationPageSizeSelector={[...new Set([pageSize, 10, 20, 50, 100])].sort((a, b) => a - b)}
        suppressCellFocus
        overlayNoRowsTemplate={`<span>${emptyText}</span>`}
        onRowClicked={(e: RowClickedEvent<T>) => e.data && onRowClicked?.(e.data)}
        {...gridOptions}
      />
    </Box>
  );
}

export default CustomAgGrid;