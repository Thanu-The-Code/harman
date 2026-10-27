import { IconButton, MenuItem, Select, Tooltip } from "@mui/material";
import UndoIcon from "@mui/icons-material/Undo";
import RedoIcon from "@mui/icons-material/Redo";
import FormatBoldIcon from "@mui/icons-material/FormatBold";
import FormatItalicIcon from "@mui/icons-material/FormatItalic";
import FormatUnderlinedIcon from "@mui/icons-material/FormatUnderlined";
import StrikethroughSIcon from "@mui/icons-material/StrikethroughS";
import CodeIcon from "@mui/icons-material/Code";
import FormatClearIcon from "@mui/icons-material/FormatClear";
import FormatAlignLeftIcon from "@mui/icons-material/FormatAlignLeft";
import FormatAlignCenterIcon from "@mui/icons-material/FormatAlignCenter";
import FormatAlignRightIcon from "@mui/icons-material/FormatAlignRight";
import FormatListBulletedIcon from "@mui/icons-material/FormatListBulleted";
import FormatListNumberedIcon from "@mui/icons-material/FormatListNumbered";
import DataObjectIcon from "@mui/icons-material/DataObject";
import FormatQuoteIcon from "@mui/icons-material/FormatQuote";
import HorizontalRuleIcon from "@mui/icons-material/HorizontalRule";
import RemoveIcon from "@mui/icons-material/Remove";
import AddIcon from "@mui/icons-material/Add";
import type { ReactNode } from "react";
import { ElementStore } from "../../vendor/react-form-builder";
import type { LayoutItem } from "../../api/formats.api";
import { activeEditor, formatSelection, toPlainHtml } from "./richText";

/**
 * The text toolbar above the page (Figma: Document create). With text selected in a
 * text element's content (Field Properties), the commands format the selection; with a
 * text element selected but no text, they apply to the whole element. Alignment also
 * works for fields. Undo / redo step through the canvas history.
 */

const TEXT_ELEMENTS = new Set(["Header", "Label", "Paragraph"]);

const STYLES = [
  { value: "p", label: "Body Text" },
  { value: "h1", label: "Heading 1" },
  { value: "h2", label: "Heading 2" },
  { value: "h3", label: "Heading 3" },
  { value: "blockquote", label: "Quote" },
];

interface Props {
  selected: LayoutItem | null;
  undo: () => void;
  redo: () => void;
  canUndo: boolean;
  canRedo: boolean;
  zoom: number;
  onZoom: (zoom: number) => void;
  onFieldSettings: () => void;
  disabled?: boolean;
}

/** Save a change made to the selected element straight into the builder's store. */
const saveElement = () => ElementStore.dispatch("updateOrder", [...(ElementStore.state.data ?? [])]);

const wrap = (html: string, tag: string) => `<${tag}>${html}</${tag}>`;

const TextToolbar = ({ selected, undo, redo, canUndo, canRedo, zoom, onZoom, onFieldSettings, disabled }: Props) => {
  const isText = !!selected && TEXT_ELEMENTS.has(String(selected.element));
  const editor = isText ? activeEditor(selected?.id) : null;

  /** A command for the selection in the content editor, else a change to the whole element. */
  const run = (command: string, value: string | undefined, whole: (el: LayoutItem) => void) => {
    if (editor) {
      formatSelection(editor, command, value);
      return;
    }
    if (!selected) return;
    whole(selected);
    saveElement();
  };
  const content = (el: LayoutItem) => String(el.content ?? "");

  const btn = (label: string, icon: ReactNode, onClick: () => void, enabled = isText) => (
    <Tooltip title={label} key={label}>
      <span>
        <IconButton
          size="small"
          className="tt-btn"
          aria-label={label}
          disabled={disabled || !enabled}
          // keep the selection in the content editor
          onMouseDown={(e) => e.preventDefault()}
          onClick={onClick}
        >
          {icon}
        </IconButton>
      </span>
    </Tooltip>
  );

  const align = (side: "left" | "center" | "right") => () => {
    if (editor) {
      formatSelection(editor, side === "left" ? "justifyLeft" : side === "center" ? "justifyCenter" : "justifyRight");
      return;
    }
    if (!selected) return;
    selected.text_align = side === "left" ? null : side;
    saveElement();
  };
  const alignActive = (side: string) => (selected?.text_align ?? "left") === side;

  return (
    // data-rfb-keep-edit: using the toolbar does not close the element being edited
    <div className="text-toolbar" data-rfb-keep-edit>
      <div className="tt-group">
        {btn("Undo", <UndoIcon fontSize="small" />, () => (editor ? formatSelection(editor, "undo") : undo()), canUndo || !!editor)}
        {btn("Redo", <RedoIcon fontSize="small" />, () => (editor ? formatSelection(editor, "redo") : redo()), canRedo || !!editor)}
      </div>
      <span className="tt-sep" />
      <Select
        size="small"
        className="tt-style"
        value=""
        displayEmpty
        disabled={disabled || !isText}
        renderValue={() => "Body Text"}
        inputProps={{ "aria-label": "Text style" }}
        onChange={(e) => {
          const tag = String(e.target.value);
          run("formatBlock", tag, (el) => {
            el.content = tag === "p" ? toPlainHtml(content(el)) : wrap(toPlainHtml(content(el)), tag);
          });
        }}
      >
        {STYLES.map((s) => (
          <MenuItem key={s.value} value={s.value}>
            {s.label}
          </MenuItem>
        ))}
      </Select>
      <span className="tt-sep" />
      <div className="tt-group">
        {btn("Bold", <FormatBoldIcon fontSize="small" />, () => run("bold", undefined, (el) => (el.bold = !el.bold)))}
        {btn("Italic", <FormatItalicIcon fontSize="small" />, () => run("italic", undefined, (el) => (el.italic = !el.italic)))}
        {btn("Underline", <FormatUnderlinedIcon fontSize="small" />, () => run("underline", undefined, (el) => (el.content = wrap(content(el), "u"))))}
        {btn("Strikethrough", <StrikethroughSIcon fontSize="small" />, () => run("strikeThrough", undefined, (el) => (el.content = wrap(content(el), "s"))))}
        {btn("Inline code", <CodeIcon fontSize="small" />, () =>
          editor
            ? formatSelection(editor, "insertHTML", `<code>${document.getSelection()?.toString() || "code"}</code>`)
            : run("", undefined, (el) => (el.content = wrap(content(el), "code"))),
        )}
        {btn("Clear formatting", <FormatClearIcon fontSize="small" />, () =>
          run("removeFormat", undefined, (el) => {
            el.content = toPlainHtml(content(el));
            el.bold = false;
            el.italic = false;
            el.text_align = null;
          }),
        )}
      </div>
      <span className="tt-sep" />
      <div className="tt-group">
        {[
          ["left", "Align left", <FormatAlignLeftIcon fontSize="small" key="l" />],
          ["center", "Align centre", <FormatAlignCenterIcon fontSize="small" key="c" />],
          ["right", "Align right", <FormatAlignRightIcon fontSize="small" key="r" />],
        ].map(([side, label, icon]) => (
          <span key={side as string} className={alignActive(side as string) && selected ? "tt-active" : ""}>
            {btn(label as string, icon as ReactNode, align(side as "left" | "center" | "right"), !!selected)}
          </span>
        ))}
        {btn("Bulleted list", <FormatListBulletedIcon fontSize="small" />, () =>
          run("insertUnorderedList", undefined, (el) => (el.content = `<ul><li>${toPlainHtml(content(el))}</li></ul>`)),
        )}
        {btn("Numbered list", <FormatListNumberedIcon fontSize="small" />, () =>
          run("insertOrderedList", undefined, (el) => (el.content = `<ol><li>${toPlainHtml(content(el))}</li></ol>`)),
        )}
      </div>
      <span className="tt-sep" />
      <div className="tt-group">
        {btn("Code block", <DataObjectIcon fontSize="small" />, () =>
          run("formatBlock", "pre", (el) => (el.content = wrap(toPlainHtml(content(el)), "pre"))),
        )}
        {btn("Quote", <FormatQuoteIcon fontSize="small" />, () =>
          run("formatBlock", "blockquote", (el) => (el.content = wrap(toPlainHtml(content(el)), "blockquote"))),
        )}
        {btn("Horizontal line", <HorizontalRuleIcon fontSize="small" />, () => (editor ? formatSelection(editor, "insertHorizontalRule") : undefined), !!editor)}
      </div>

      <div className="tt-right">
        <div className="tt-zoom" aria-label="Zoom">
          {btn("Zoom out", <RemoveIcon fontSize="small" />, () => onZoom(Math.max(50, zoom - 10)), zoom > 50)}
          <span className="tt-zoom-value">{zoom}</span>
          {btn("Zoom in", <AddIcon fontSize="small" />, () => onZoom(Math.min(200, zoom + 10)), zoom < 200)}
        </div>
        <button type="button" className="tt-settings" onClick={onFieldSettings} disabled={!selected}>
          Field Setting
        </button>
      </div>
    </div>
  );
};

export default TextToolbar;
