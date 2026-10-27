import React from 'react';
import { Collapse } from '@mui/material';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import FolderIcon from '@mui/icons-material/Folder';
import DragIndicatorOutlinedIcon from "@mui/icons-material/DragIndicatorOutlined";
import PushPinIcon from '@mui/icons-material/PushPin';
import type { FolderNode } from '../constants/types';

interface Props {
  nodes: FolderNode[];
  selectedPath: string;
  expanded: Set<string>;
  pinnedFolders: Set<string>;
  onSelect: (node: FolderNode, path: string) => void;
  onContextMenu: (
    node: FolderNode,
    path: string,
    anchor: HTMLElement,
  ) => void;
  onToggle: (path: string) => void;
  parentPath?: string;
}

const FolderTree: React.FC<Props> = ({
  nodes,
  selectedPath,
  expanded,
  pinnedFolders,
  onSelect,
  onContextMenu,
  onToggle,
  parentPath = '',
}) => (
  <>
    {nodes.map((node) => {
      const path = parentPath ? `${parentPath}/${node.id}` : node.id;
      const hasChildren = !!node.children?.length;
      const isOpen = hasChildren && expanded.has(path);

      return (
        <div key={node.id}>
          <div
            className={`tree-row ${selectedPath === path ? 'selected' : ''}`}
            role="button"
            tabIndex={0}
            aria-label={`Select ${node.name}`}
            onClick={() => onSelect(node, path)}
            onContextMenu={(event) => {
              event.preventDefault();
              onContextMenu(node, path, event.currentTarget);
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                onSelect(node, path);
              } else if (event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) {
                event.preventDefault();
                onContextMenu(node, path, event.currentTarget);
              }
            }}
          >
            <span
              style={{ display: 'flex' }}
              onClick={(event) => {
                event.stopPropagation();
                if (hasChildren) onToggle(path);
              }}
              aria-hidden="true"
            >
              {isOpen ? (
                <ExpandMoreIcon className="tree-chevron" />
              ) : hasChildren ? (
                <ChevronRightIcon className="tree-chevron" />
              ) : (
                <span className="tree-chevron-spacer" />
              )}
            </span>
            <FolderIcon className="tree-folder-icon" />
            <span className="tree-folder-name">{node.name}</span>
            {pinnedFolders.has(node.id) && (
              <PushPinIcon className="tree-pin-icon" fontSize="small" />
            )}
            {selectedPath === path && (
              <DragIndicatorOutlinedIcon
                className="tree-drag-indicator"
                fontSize="small"
                aria-hidden="true"
              />
            )}
          </div>

          {hasChildren && (
            <Collapse in={isOpen} unmountOnExit>
              <div className="tree-children">
                <FolderTree
                  nodes={node.children!}
                  parentPath={path}
                  selectedPath={selectedPath}
                  expanded={expanded}
                  pinnedFolders={pinnedFolders}
                  onSelect={onSelect}
                  onContextMenu={onContextMenu}
                  onToggle={onToggle}
                />
              </div>
            </Collapse>
          )}
        </div>
      );
    })}
  </>
);

export default FolderTree;
