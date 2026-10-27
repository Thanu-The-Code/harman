import type { SxProps, Theme } from '@mui/material/styles';

export const customAgGridStyles: SxProps<Theme> = {
  width: '100%',
  height: '100%',
  minHeight: 240,

  '& .ag-root-wrapper': { border: 'none', borderRadius: 0 },
  '& .ag-header': { borderTop: '1px solid #e5e7eb' },
  '& .ag-header-cell-label': { fontWeight: 500 },

  /* vertically centre every cell; wrapped text cells fall back to block */
  '& .ag-cell': { display: 'flex', alignItems: 'center' },
  '& .ag-cell.ag-cell-wrap-text': {
    display: 'block',
    lineHeight: 1.4,
    paddingTop: '12px',
    paddingBottom: '12px',
    wordBreak: 'normal',
  },
  '& .ag-row': { borderColor: '#e5e7eb' },
  '& .ag-row-hover': { background: '#f9fafb' },
  '& .ag-overlay-no-rows-center': { fontSize: 13, color: '#6b7280' },
};