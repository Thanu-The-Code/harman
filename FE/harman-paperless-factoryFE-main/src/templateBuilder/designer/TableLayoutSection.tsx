import { useState } from "react";
import { Button, Dialog, IconButton } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import OpenInFullIcon from "@mui/icons-material/OpenInFull";
import TableEditor from "../../vendor/react-form-builder/table-editor";
import { bodyGrid, isInput, type TableElementLike } from "../../vendor/react-form-builder/table-model";

/** Tables up to this many columns are also edited in the side panel; wider ones only in the large editor. */
const INLINE_COLUMNS = 8;

interface Props {
  element: TableElementLike;
  /** typing: the element changed; save once typing pauses */
  onChange: () => void;
  /** a structural edit (merge, add a row, input type): save now */
  onStructureChange: () => void;
  onCommit: () => void;
}

/**
 * Field Properties -> Table layout. The side panel shows the table's size; the table itself
 * is edited in a large editor (a check sheet read from a scan easily has 38 columns), and a
 * narrow table also right in the panel.
 */
const TableLayoutSection = ({ element, onChange, onStructureChange, onCommit }: Props) => {
  const [open, setOpen] = useState(false);
  const columns = element.columns?.length ?? 0;
  const rows = element.rows?.length ?? 0;
  const inputs = bodyGrid(element).reduce((n, row) => n + row.filter((cell) => isInput(cell)).length, 0);

  const editor = (
    <TableEditor element={element} onChange={onChange} onStructureChange={onStructureChange} onCommit={onCommit} />
  );

  return (
    <>
      <div className="fp-table-summary">
        <span>
          {columns} columns · {rows} rows · {inputs} cells to fill in
        </span>
        <Button size="small" startIcon={<OpenInFullIcon fontSize="small" />} onClick={() => setOpen(true)}>
          Edit table
        </Button>
      </div>
      {element.reference && inputs === 0 && (
        <div className="fp-hint">Printed for reference, as on the paper form: nothing in this table is filled in.</div>
      )}
      {columns <= INLINE_COLUMNS ? (
        <div className="fp-table-editor">{editor}</div>
      ) : (
        <div className="fp-hint">
          Choose a cell to make it printed text or an input (text, number, date, ✓ / ✗), give a number cell its limits,
          merge cells, or add rows and columns.
        </div>
      )}

      <Dialog
        open={open}
        onClose={() => {
          onCommit();
          setOpen(false);
        }}
        fullWidth
        maxWidth="xl"
        className="table-editor-dialog rfb-scope"
        // part of the field being edited: using it does not close the field's properties
        slotProps={{ root: { "data-rfb-keep-edit": "" } as object }}
      >
        <div className="ted-head">
          <div>
            <h2>Table layout</h2>
            <p>
              {columns} columns · {rows} rows · {inputs} cells to fill in. Changes are saved as you make them.
            </p>
          </div>
          <IconButton
            aria-label="Close table editor"
            onClick={() => {
              onCommit();
              setOpen(false);
            }}
          >
            <CloseIcon fontSize="small" />
          </IconButton>
        </div>
        <div className="ted-body fp-table-editor">{open && editor}</div>
      </Dialog>
    </>
  );
};

export default TableLayoutSection;
