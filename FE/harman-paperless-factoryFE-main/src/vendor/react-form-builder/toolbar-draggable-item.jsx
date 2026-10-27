/**
  * <ToolbarItem />
  */

import React from 'react';
import { useDrag } from 'react-dnd';
import ItemTypes from './ItemTypes';
import ID from './UUID';

const ToolbarItem = ({ data, onCreate, onClick }) => {
  // Setup drag functionality using the useDrag hook
  const [{ isDragging }, drag] = useDrag({
    type: ItemTypes.CARD,
    item: () => ({
      id: ID.uuid(),
      index: -1,
      data: data,
      onCreate: onCreate,
    }),
    collect: (monitor) => ({
      isDragging: monitor.isDragging(),
    }),
  });

  // Apply slight opacity while dragging for better UX
  const opacity = isDragging ? 0.5 : 1;

  return (
    <li 
      ref={drag} 
      onClick={onClick} 
      style={{ opacity, cursor: 'move' }}
    >
      {/* iconNode: a React icon given by the host app; icon: a Font Awesome class */}
      {data.iconNode ? <span className="rfb-tile-icon">{data.iconNode}</span> : <i className={data.icon}></i>}
      <span className="rfb-tile-name">{data.name}</span>
    </li>
  );
};

export default ToolbarItem;