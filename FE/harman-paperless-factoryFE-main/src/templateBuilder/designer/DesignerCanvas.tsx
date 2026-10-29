import { useCallback, useEffect, useRef, useState, type SyntheticEvent } from "react";
import { Preview, Registry, type EditFormProps } from "../../vendor/react-form-builder";
import type { LayoutItem } from "../../api/formats.api";

interface Props {
  /** The layout the canvas opens with (later changes come back through onChange). */
  initialData: LayoutItem[];
  onChange: (data: LayoutItem[]) => void;
  /** Where the selected element's properties are drawn (the side panel's Field Properties tab). */
  propertiesContainer: HTMLElement | null;
  renderProperties: (props: EditFormProps) => React.ReactNode;
  /** The element being edited (null when none). */
  onSelect: (element: LayoutItem | null) => void;
  zoom: number;
}

/**
 * The page the template is drawn on: the builder's sortable canvas. Choosing an element's
 * edit button selects it; its properties render in the side panel, not over the canvas.
 * Must sit inside <BuilderProvider> together with the palette.
 */
const DesignerCanvas = ({ initialData, onChange, propertiesContainer, renderProperties, onSelect, zoom }: Props) => {
  const [editElement, setEditElement] = useState<LayoutItem | null>(null);
  // the builder keeps its own store; it calls back with every saved change
  const changeRef = useRef(onChange);
  useEffect(() => {
    changeRef.current = onChange;
  }, [onChange]);
  const onPost = useCallback(({ task_data }: { task_data: LayoutItem[] }) => changeRef.current(task_data.filter(Boolean)), []);

  const select = (element: LayoutItem | null) => {
    setEditElement(element);
    onSelect(element);
  };
  const geometry = initialData.find((item) => item.layout_position && item.layout_page_size)?.layout_page_size as
    | [number, number]
    | undefined;
  const pageCount = Number(initialData.find((item) => item.layout_page_count)?.layout_page_count ?? 1);
  const excelLayout = Boolean(geometry);

  // the edit button toggles that element; clicking an element (selectOnly) selects it;
  // either way another element is switched to straight away
  const editModeOn = (data: LayoutItem, e: SyntheticEvent & { selectOnly?: boolean }) => {
    e.preventDefault();
    e.stopPropagation();
    const same = !!editElement && editElement.id === data.id;
    if (e.selectOnly) {
      if (!same) select(data);
      return;
    }
    select(same ? null : data);
  };

  return (
    // react-form-builder: the builder's own canvas styles (drag cursor, hover toolbar, disabled inputs)
    <div className={`react-form-builder designer-sheet${excelLayout ? " designer-sheet-geometry" : ""}`} style={{ zoom: zoom / 100 }}>
      {/* outline the element being edited (the builder marks no selection itself) */}
      {editElement && (
        <style>{`.designer-sheet .rfb-card[data-id="${CSS.escape(String(editElement.id))}"] > div > .rfb-item,
          .designer-sheet .rfb-child[data-id="${CSS.escape(String(editElement.id))}"] > .rfb-item {
          border: 1px solid #14b8a6 !important; box-shadow: 0 0 0 3px rgba(20, 184, 166, 0.12); }`}</style>
      )}
      <div
        className={excelLayout ? "designer-preview-geometry" : undefined}
        style={geometry ? { aspectRatio: `${geometry[0]} / ${geometry[1] * pageCount}` } : undefined}
      >
        <Preview
          className={`react-form-builder-preview designer-preview${excelLayout ? " designer-preview-geometry-inner" : ""}`}
          data={initialData}
          onPost={onPost}
          saveAlways
          editMode={!!editElement}
          editElement={editElement}
          editModeOn={editModeOn}
          manualEditModeOff={() => select(null)}
          parent={{ manualEditModeOff: () => select(null) }}
          registry={Registry}
          variables={{}}
          renderEditForm={renderProperties}
          editFormContainer={propertiesContainer}
        />
      </div>
    </div>
  );
};

export default DesignerCanvas;
