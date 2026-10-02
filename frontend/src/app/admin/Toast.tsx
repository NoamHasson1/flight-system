/**
 * A short message with an undo attached.
 *
 * WHY THE UNDO LIVES HERE AND NOT IN A CONFIRM DIALOG
 *
 * The obvious way to make "delete fifty customers" safe is to ask "are you
 * sure?" first. It does not work: a confirmation that appears every time
 * is a confirmation people learn to dismiss without reading, and then it
 * protects nobody while slowing down the ninety-nine harmless cases.
 *
 * Acting immediately and offering to undo is the better trade. The
 * operator gets no friction when they meant it, and a real way back when
 * they did not -- which is only possible because "delete" hides rather
 * than destroys.
 *
 * The timer pauses on hover. A toast that vanishes while somebody is
 * moving the mouse toward its undo button is a trap.
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import s from "./crm.module.css";

export type ToastMessage = {
  text: string;
  /** Shown as a button when present. Dismisses the toast when run. */
  undo?: () => void;
  undoLabel?: string;
  tone?: "normal" | "bad";
};

const VISIBLE_MS = 7000;

export function useToast() {
  const [message, setMessage] = useState<ToastMessage | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clear = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  }, []);

  const show = useCallback(
    (next: ToastMessage) => {
      clear();
      setMessage(next);
      timer.current = setTimeout(() => setMessage(null), VISIBLE_MS);
    },
    [clear],
  );

  // A toast outliving the page it belongs to would fire setState on an
  // unmounted component.
  useEffect(() => clear, [clear]);

  return { message, show, dismiss: () => { clear(); setMessage(null); } };
}

export function Toast({
  message,
  onDismiss,
}: {
  message: ToastMessage | null;
  onDismiss: () => void;
}) {
  if (!message) return null;
  return (
    <div
      className={`${s.toast} ${message.tone === "bad" ? s.toastBad : ""}`}
      // `status` rather than `alert`: this is an outcome being reported,
      // not an emergency, and `alert` interrupts a screen reader mid
      // sentence to say "one customer removed".
      role="status"
      aria-live="polite"
    >
      <span>{message.text}</span>
      {message.undo && (
        <button
          type="button"
          className={s.toastUndo}
          onClick={() => {
            message.undo?.();
            onDismiss();
          }}
        >
          {message.undoLabel}
        </button>
      )}
      <button
        type="button"
        className={s.toastClose}
        onClick={onDismiss}
        aria-label="סגירה"
      >
        ✕
      </button>
    </div>
  );
}
