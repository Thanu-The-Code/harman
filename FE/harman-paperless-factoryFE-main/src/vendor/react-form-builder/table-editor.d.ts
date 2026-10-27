import * as React from "react";

/** The Table element's structure editor: headings, merged cells, fixed text and input cells. */
export default class TableEditor extends React.Component<{
  element: unknown;
  /** typing: the element changed but is not saved yet */
  onChange: () => void;
  /** a structural edit (merge, add a row): save now */
  onStructureChange: () => void;
  /** a text field lost focus: save */
  onCommit: () => void;
}> {}
