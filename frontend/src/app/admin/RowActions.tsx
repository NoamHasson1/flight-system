/**
 * The two send buttons at the end of a customer's row.
 *
 * WHY IN THE ROW AND NOT ONLY ON THE CUSTOMER'S PAGE
 *
 * Both actions are also on that page, and that is the right place when
 * somebody is reading one claim. But the commonest shape of this work is
 * going down the list: three people are missing receipts, two are owed
 * their pleading. Opening a tab per person to send one email turns a
 * two-minute pass into twenty.
 *
 * SO THE ROW OPENS A DIALOG, NOT A TAB. The forms are the same ones the
 * page uses -- one implementation, so the wording and the confirmation
 * cannot drift between the two places they are reached from.
 *
 * Both buttons stop the click from reaching the row. The row opens the
 * customer in a new tab, and a button that also did that would throw a
 * tab at somebody every time they tried to send an email.
 */

"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { strings } from "@/lib/strings";
import { RequestItemsForm, StatementForm } from "./OutreachForms";
import s from "./crm.module.css";

type Which = "request" | "statement";

export function RowActions({
  adminKey,
  claimId,
  email,
  name,
  onDone,
}: {
  adminKey: string;
  /** Null when the customer never filed. Both actions need a claim. */
  claimId: string | null;
  email: string | null;
  name: string | null;
  /**
   * `storedFile` is true when the send also wrote a document to the
   * claim. The list shows a file count, and a row that says "no files"
   * seconds after an operator attached one teaches them not to trust the
   * column.
   */
  onDone: (message: string, storedFile: boolean) => void;
}) {
  const t = strings.admin.outreach;
  const [open, setOpen] = useState<Which | null>(null);

  // Nothing to send to, or nothing to send about. Shown as a dash rather
  // than as two dead buttons: a disabled control invites a click and
  // then explains nothing.
  if (!claimId || !email) {
    return <span className={s.muted}>—</span>;
  }

  return (
    <span
      className={s.rowActions}
      // The row opens a tab. These do not.
      onClick={(e) => e.stopPropagation()}
    >
      <button
        type="button"
        className={s.iconButton}
        title={t.requestTitle}
        aria-label={t.requestTitle}
        onClick={() => setOpen("request")}
      >
        <MailIcon />
      </button>
      <button
        type="button"
        className={s.iconButton}
        title={t.statementTitle}
        aria-label={t.statementTitle}
        onClick={() => setOpen("statement")}
      >
        <UploadIcon />
      </button>

      {open && (
        <Dialog
          title={open === "request" ? t.requestTitle : t.statementTitle}
          subtitle={`${name ?? ""} · ${email}`.trim()}
          onClose={() => setOpen(null)}
        >
          {open === "request" ? (
            <RequestItemsForm
              adminKey={adminKey}
              claimId={claimId}
              email={email}
              onDone={(m) => {
                setOpen(null);
                onDone(m, false);
              }}
            />
          ) : (
            <StatementForm
              adminKey={adminKey}
              claimId={claimId}
              email={email}
              onDone={(m) => {
                setOpen(null);
                onDone(m, true);
              }}
            />
          )}
        </Dialog>
      )}
    </span>
  );
}

/**
 * PORTALLED TO THE BODY, and it has to be.
 *
 * This renders from inside a `<td>`. A dialog declared there is laid out
 * inside a table cell -- and the table scrolls sideways in its own
 * container, so the dialog would be clipped by the column it was opened
 * from. The same lesson as the document lightbox: `inset: 0` only means
 * the viewport when nothing above it has made a new containing block.
 */
function Dialog({
  title,
  subtitle,
  onClose,
  children,
}: {
  title: string;
  subtitle: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    panel.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return createPortal(
    <>
      <div className={s.scrim} onClick={onClose} aria-hidden />
      <div
        ref={panel}
        className={s.dialog}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
      >
        <header className={s.dialogHead}>
          <div>
            <h2 className={s.dialogTitle}>{title}</h2>
            {/* The recipient, on screen the whole time. These forms send
                mail in our name, and knowing who it is going to should
                not require remembering which row was clicked. */}
            <p className={s.dialogSub}>{subtitle}</p>
          </div>
          <button type="button" className={s.ghost} onClick={onClose}>
            {strings.admin.files.close}
          </button>
        </header>
        <div className={s.dialogBody}>{children}</div>
      </div>
    </>,
    document.body,
  );
}

function MailIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden>
      <rect
        x="1.6"
        y="3.4"
        width="12.8"
        height="9.2"
        rx="1.8"
        stroke="currentColor"
        strokeWidth="1.4"
      />
      <path
        d="M2.4 4.6 8 8.8l5.6-4.2"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function UploadIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path
        d="M8 10.6V2.4M8 2.4 5 5.4M8 2.4l3 3"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M2.4 10.2v2.2a1.4 1.4 0 0 0 1.4 1.4h8.4a1.4 1.4 0 0 0 1.4-1.4v-2.2"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
      />
    </svg>
  );
}
