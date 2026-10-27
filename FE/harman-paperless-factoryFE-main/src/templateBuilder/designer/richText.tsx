/* eslint-disable react-refresh/only-export-components */
import { useEffect, useRef } from "react";
import myxss from "../../vendor/react-form-builder/form-elements/myxss";

/**
 * Rich text for the designer's text elements (Header, Label, Paragraph). The content
 * is edited in Field Properties; the text toolbar formats the selection there. The
 * last selection inside an editor is remembered, so a toolbar control that takes the
 * focus (the style list) still formats what was selected.
 */

let lastRange: Range | null = null;
let lastEditor: HTMLElement | null = null;

if (typeof document !== "undefined") {
  document.addEventListener("selectionchange", () => {
    const sel = document.getSelection();
    if (!sel || !sel.rangeCount) return;
    const node = sel.anchorNode;
    const editor = (node instanceof Element ? node : node?.parentElement)?.closest<HTMLElement>(".rich-text-editor");
    if (editor) {
      lastEditor = editor;
      lastRange = sel.getRangeAt(0).cloneRange();
    }
  });
}

/** The editor of this element, if its content is being edited (it is in the page). */
export const activeEditor = (elementId?: string | null) =>
  lastEditor && lastEditor.isConnected && (!elementId || lastEditor.dataset.elementId === elementId) ? lastEditor : null;

/**
 * Run a formatting command on the remembered selection of `editor`
 * (bold, insertUnorderedList, formatBlock, justifyCenter, ...). The editor's input
 * event follows, which saves the content.
 */
export const formatSelection = (editor: HTMLElement, command: string, value?: string) => {
  editor.focus();
  const sel = document.getSelection();
  if (sel && lastRange && editor.contains(lastRange.commonAncestorContainer)) {
    sel.removeAllRanges();
    sel.addRange(lastRange);
  }
  // execCommand is the one editing API that works on any selection in contentEditable;
  // it is deprecated in name only and supported by every current browser
  document.execCommand(command, false, value);
};

interface EditorProps {
  elementId: string;
  html: string;
  onChange: (html: string) => void;
  label: string;
}

/** A contentEditable box; its HTML is set when the element changes, not on every keystroke (that would move the caret). */
export const RichTextEditor = ({ elementId, html, onChange, label }: EditorProps) => {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.innerHTML = myxss.process(html); // only the formatting the toolbar makes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [elementId]);
  return (
    <div
      ref={ref}
      className="rich-text-editor"
      data-element-id={elementId}
      contentEditable
      suppressContentEditableWarning
      role="textbox"
      aria-multiline="true"
      aria-label={label}
      onInput={(e) => onChange((e.target as HTMLDivElement).innerHTML)}
    />
  );
};

/** Strip markup: the "clear formatting" of a whole element. */
export const toPlainHtml = (html: string) => {
  const text = (new DOMParser().parseFromString(html, "text/html").body.textContent ?? "").trim();
  return text.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]!);
};
