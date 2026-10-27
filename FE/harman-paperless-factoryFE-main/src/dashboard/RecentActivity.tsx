import { Box, ButtonBase, Link, Paper, Typography } from '@mui/material';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import DescriptionOutlinedIcon from '@mui/icons-material/DescriptionOutlined';
import GroupsOutlinedIcon from '@mui/icons-material/GroupsOutlined';
import PersonAddAltOutlinedIcon from '@mui/icons-material/PersonAddAltOutlined';
// import EditNoteOutlinedIcon from '@mui/icons-material/EditNoteOutlined';
import ShareOutlinedIcon from '@mui/icons-material/ShareOutlined';
import type { ReactElement } from 'react';
import type { ActivityItem } from './types';

const ICONS: Record<ActivityItem['type'], ReactElement> = {
  template: <DescriptionOutlinedIcon fontSize="small" />,
  team: <GroupsOutlinedIcon fontSize="small" />,
  person: <PersonAddAltOutlinedIcon fontSize="small" />,
  resource: <ShareOutlinedIcon fontSize="small" />,
  record: <DescriptionOutlinedIcon fontSize="small" />,
  approval: <DescriptionOutlinedIcon fontSize="small" />,
};

interface Props {
  items: ActivityItem[];
  onItemClick?: (item: ActivityItem) => void;
  onViewAll?: () => void;
}

export default function RecentActivity({ items, onItemClick, onViewAll }: Props) {
  return (
    <Paper variant="outlined" sx={{ p: 2, borderRadius: 2, borderColor: '#e5e7eb', height: '100%' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5 }}>
        <Typography sx={{ fontSize: 13, fontWeight: 600 }}>Recent Activity</Typography>
        <Link component="button" underline="none" onClick={onViewAll} sx={{ fontSize: 12, color: '#14b8a6' }}>
          View All
        </Link>
      </Box>
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        {items.map((item) => (
          <ButtonBase
            key={item.id}
            onClick={() => onItemClick?.(item)}
            sx={{
              display: 'flex', alignItems: 'center', gap: 1.25, p: 1.25, width: '100%',
              justifyContent: 'flex-start', textAlign: 'left',
              border: '1px solid #e5e7eb', borderRadius: 1.5,
              '&:hover': { bgcolor: '#f9fafb' },
            }}
          >
            <Box
              sx={{
                width: 28, height: 28, borderRadius: 1, bgcolor: '#e6f7f5', color: '#14b8a6',
                display: 'grid', placeItems: 'center', flexShrink: 0,
              }}
            >
              {ICONS[item.type]}
            </Box>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography sx={{ fontSize: 12, fontWeight: 600 }} noWrap>{item.title}</Typography>
              <Typography sx={{ fontSize: 11, color: '#9ca3af' }}>{item.time}</Typography>
            </Box>
            <ChevronRightIcon fontSize="small" sx={{ color: '#6b7280' }} />
          </ButtonBase>
        ))}
      </Box>
    </Paper>
  );
}
