/* eslint-disable react-refresh/only-export-components */
import { Button, IconButton } from '@mui/material';
import VisibilityOutlinedIcon from '@mui/icons-material/VisibilityOutlined';
import type { ColDef, ICellRendererParams } from 'ag-grid-community';
import RagDot from '../status/RagDot';
import type { DocumentListItem } from '../../api/records.api';
import { formatDate } from '../../utils/date';

/* ---------- cell renderers ---------- */
const NameCell = ({ data }: ICellRendererParams<DocumentListItem>) =>
  data ? (
    <div className="approval-cell">
      <div className="approval-title">{data.document_name}</div>
      <div className="approval-by">{data.number}</div>
    </div>
  ) : null;

const StatusCell = ({ data }: ICellRendererParams<DocumentListItem>) =>
  data ? (
    <div className="approval-cell">
      <div className="approval-title">{data.stage_label}</div>
      {data.awaiting && (
        <div className="approval-by">
          {data.awaiting.overdue ? 'Overdue · ' : ''}
          {data.awaiting.people.map((p) => p.name).join(', ')}
        </div>
      )}
    </div>
  ) : null;

const ApprovalCell = ({ data }: ICellRendererParams<DocumentListItem>) =>
  data?.last_approval ? (
    <div className="approval-cell">
      <div className="approval-title">{`${data.last_approval.order}. ${data.last_approval.name}`}</div>
      <div className="approval-by">by {data.last_approval.by}</div>
    </div>
  ) : (
    <span className="approval-by">—</span>
  );

interface ActionProps extends ICellRendererParams<DocumentListItem> {
  onTrack: (row: DocumentListItem) => void;
  onView: (row: DocumentListItem) => void;
}

const ActionCell = ({ data, onTrack, onView }: ActionProps) =>
  data ? (
    <div className="action-cell">
      <Button className="track-btn" size="small" onClick={() => onTrack(data)}>
        Track Status
      </Button>
      <IconButton className="eye-btn" size="small" aria-label={`Open ${data.number}`} onClick={() => onView(data)}>
        <VisibilityOutlinedIcon fontSize="small" />
      </IconButton>
    </div>
  ) : null;

/* ---------- column definitions ---------- */
interface Handlers {
  onTrack: (row: DocumentListItem) => void;
  onView: (row: DocumentListItem) => void;
}

/** My Documents: records the person filled or is involved in. */
export const getColumns = ({ onTrack, onView }: Handlers): ColDef<DocumentListItem>[] => [
  {
    headerName: '',
    width: 56,
    cellRenderer: ({ data }: ICellRendererParams<DocumentListItem>) => (data ? <RagDot rag={data.rag} /> : null),
  },
  { headerName: 'Name', flex: 1.7, minWidth: 230, cellRenderer: NameCell, autoHeight: true },
  { headerName: 'Department', flex: 1.2, minWidth: 150, valueGetter: (p) => p.data?.department?.name ?? '—' },
  { field: 'type', headerName: 'Type', flex: 0.8, minWidth: 100 },
  { headerName: 'Start On', flex: 0.9, minWidth: 120, valueGetter: (p) => formatDate(p.data?.start_on) },
  { headerName: 'Last Update', flex: 0.9, minWidth: 120, valueGetter: (p) => formatDate(p.data?.last_update) },
  { headerName: 'Status', flex: 1.3, minWidth: 170, cellRenderer: StatusCell, autoHeight: true },
  { headerName: 'Last Approval', flex: 1.4, minWidth: 190, cellRenderer: ApprovalCell, autoHeight: true },
  {
    headerName: 'Action',
    flex: 1.3,
    minWidth: 200,
    headerClass: 'ag-center-header',
    cellRenderer: ActionCell,
    cellRendererParams: { onTrack, onView },
  },
];
