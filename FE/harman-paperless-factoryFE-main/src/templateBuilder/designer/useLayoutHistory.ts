import { useCallback, useRef, useState } from "react";
import { ElementStore } from "../../vendor/react-form-builder";
import type { LayoutItem } from "../../api/formats.api";

const LIMIT = 60;

/**
 * Undo / redo for the canvas. Every change the builder saves is recorded as a snapshot;
 * undo and redo put a snapshot back into the builder's store (custom element components
 * are looked up again by key when the canvas renders, so JSON snapshots are enough).
 */
export const useLayoutHistory = () => {
  const past = useRef<string[]>([]);
  const future = useRef<string[]>([]);
  const replaying = useRef(false);
  // what the undo / redo buttons show; the snapshots themselves live in refs
  const [depth, setDepth] = useState({ past: 0, future: 0 });
  const changed = () => setDepth({ past: past.current.length, future: future.current.length });

  /** Call with every layout the builder saves (and once with the starting layout). */
  const record = useCallback((data: LayoutItem[]) => {
    if (replaying.current) {
      replaying.current = false;
      return;
    }
    const snapshot = JSON.stringify(data);
    if (past.current[past.current.length - 1] === snapshot) return;
    past.current.push(snapshot);
    if (past.current.length > LIMIT) past.current.shift();
    future.current = [];
    changed();
  }, []);

  const apply = useCallback((snapshot: string) => {
    replaying.current = true;
    ElementStore.dispatch("updateOrder", JSON.parse(snapshot));
    setDepth({ past: past.current.length, future: future.current.length });
  }, []);

  const undo = useCallback(() => {
    if (past.current.length < 2) return;
    future.current.push(past.current.pop()!);
    apply(past.current[past.current.length - 1]);
  }, [apply]);

  const redo = useCallback(() => {
    const next = future.current.pop();
    if (!next) return;
    past.current.push(next);
    apply(next);
  }, [apply]);

  return { record, undo, redo, canUndo: depth.past > 1, canRedo: depth.future > 0 };
};
