/**
 * The two letters an operator sends by hand, as reusable forms.
 *
 * They are reached from two places -- a button at the end of a row in
 * the list, and a section on the customer's own page -- and they are ONE
 * implementation. Two copies of a form that sends mail to a customer
 * over a lawyer's name is two places for the wording, the confirmation
 * and the error handling to drift apart.
 *
 * Each form owns its own state and reports the outcome upwards. Neither
 * knows whether it is inside a page or a dialog, which is what makes it
 * usable in both.
 */

"use client";

import { useState } from "react";

import { requestItems, sendStatement } from "@/lib/api";
import { strings } from "@/lib/strings";
import s from "./crm.module.css";

/**
 * Both forms confirm before sending, and this is the one place in the
 * console I argue FOR a confirmation.
 *
 * Everywhere else -- deleting rows, changing a stage -- a dialog shown
 * every time is one people learn to click through, so the right answer
 * is to act and offer undo. These are different: the action leaves the
 * building. A mistaken delete comes back from the bin; a mistaken email
 * is in somebody's inbox for ever.
 *
 * The question names the recipient, because an address is something a
 * person actually reads and "are you sure?" is not.
 */
function confirmSend(question: string, to: string): boolean {
  return window.confirm(`${question}\n\n${to}`);
}

export function StatementForm({
  adminKey,
  claimId,
  email,
  onDone,
}: {
  adminKey: string;
  claimId: string;
  email: string;
  onDone: (message: string) => void;
}) {
  const t = strings.admin.outreach;
  const [file, setFile] = useState<File | null>(null);
  const [note, setNote] = useState("");
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);

  async function send() {
    if (!file || !confirmSend(t.confirmStatement, email)) return;
    setBusy(true);
    const r = await sendStatement(
      adminKey,
      claimId,
      file,
      note.trim() || undefined,
    );
    setBusy(false);
    if (!r.ok) return onDone(t.failed);
    // `sent` is whether the provider ACCEPTED it, not whether a request
    // was made. An operator told "sent" about a message that bounced
    // will wait for a reply that cannot come.
    onDone(r.data.sent ? t.statementSent(r.data.to) : t.failed);
    setFile(null);
    setNote("");
  }

  return (
    <>
      {/* A styled <label> wrapping a real file input, not a div that
          merely looks droppable. Drag-and-drop alone excludes anyone on
          a keyboard, and that is the commonest way an upload quietly
          becomes unreachable. */}
      <label
        className={`${s.drop} ${over ? s.dropOver : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          const dropped = e.dataTransfer.files?.[0];
          if (dropped) setFile(dropped);
        }}
      >
        <input
          type="file"
          accept="application/pdf,image/*"
          className="sr-only"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <span className={s.dropText}>{file ? file.name : t.dropHere}</span>
        <span className={s.dropHint}>{t.dropHint}</span>
      </label>

      <textarea
        className={s.noteBox}
        rows={2}
        value={note}
        placeholder={t.notePlaceholder}
        onChange={(e) => setNote(e.target.value)}
      />

      <button
        type="button"
        className={`${s.primary} ${s.sendButton}`}
        disabled={!file || busy}
        onClick={() => void send()}
      >
        {busy ? t.sending : t.sendStatement}
      </button>
    </>
  );
}

export function RequestItemsForm({
  adminKey,
  claimId,
  email,
  onDone,
}: {
  adminKey: string;
  claimId: string;
  email: string;
  onDone: (message: string) => void;
}) {
  const t = strings.admin.outreach;
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  async function send() {
    if (!chosen.size || !confirmSend(t.confirmRequest, email)) return;
    setBusy(true);
    const r = await requestItems(
      adminKey,
      claimId,
      [...chosen],
      note.trim() || undefined,
    );
    setBusy(false);
    if (!r.ok) return onDone(t.failed);
    onDone(r.data.sent ? t.requestSent(r.data.to) : t.failed);
    setChosen(new Set());
    setNote("");
  }

  return (
    <>
      <p className={`${s.note} ${s.requestLead}`}>{t.requestLead}</p>

      {/* A fixed list, not a text box. The same handful of things hold
          up every claim; a checklist gives the customer something clear
          instead of a sentence typed in a hurry, and it can be counted
          later. */}
      <div className={s.checkGrid}>
        {Object.entries(t.items).map(([key, label]) => (
          <label key={key} className={s.checkItem}>
            <input
              type="checkbox"
              checked={chosen.has(key)}
              onChange={() =>
                setChosen((prev) => {
                  const next = new Set(prev);
                  if (next.has(key)) next.delete(key);
                  else next.add(key);
                  return next;
                })
              }
            />
            {label}
          </label>
        ))}
      </div>

      <textarea
        className={s.noteBox}
        rows={2}
        value={note}
        placeholder={t.notePlaceholder}
        onChange={(e) => setNote(e.target.value)}
      />

      <button
        type="button"
        className={`${s.primary} ${s.sendButton}`}
        disabled={!chosen.size || busy}
        onClick={() => void send()}
      >
        {busy ? t.sending : t.sendRequest}
      </button>
    </>
  );
}
