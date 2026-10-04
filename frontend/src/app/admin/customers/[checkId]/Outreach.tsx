/**
 * The two things an operator sends to a customer by hand.
 *
 *   THE STATEMENT OF CLAIM   drop the lawyer's pleading in, it goes out
 *   A REQUEST FOR ITEMS      tick what is missing, it goes out
 *
 * BOTH CONFIRM BEFORE SENDING, and that is the one piece of friction
 * worth keeping. Everywhere else in this console I argued against
 * confirmations -- a dialog shown every time is one people learn to
 * click through. These are different: the action leaves the building.
 * A mistaken delete is undone from the bin; a mistaken email is in
 * somebody's inbox for ever, over a lawyer's name.
 *
 * So the confirm names the recipient. "Send to noam@example.com?" is a
 * question somebody actually reads, where "Are you sure?" is not.
 */

"use client";

import { useState } from "react";

import { requestItems, sendStatement } from "@/lib/api";
import { strings } from "@/lib/strings";
import s from "../../crm.module.css";

export function Outreach({
  adminKey,
  claimId,
  onDone,
}: {
  adminKey: string;
  claimId: string;
  onDone: (message: string) => void;
}) {
  return (
    <>
      <SendStatement adminKey={adminKey} claimId={claimId} onDone={onDone} />
      <RequestItems adminKey={adminKey} claimId={claimId} onDone={onDone} />
    </>
  );
}

function SendStatement({
  adminKey,
  claimId,
  onDone,
}: {
  adminKey: string;
  claimId: string;
  onDone: (message: string) => void;
}) {
  const t = strings.admin.outreach;
  const [file, setFile] = useState<File | null>(null);
  const [note, setNote] = useState("");
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);

  async function send() {
    if (!file) return;
    if (!window.confirm(t.confirmStatement)) return;
    setBusy(true);
    const r = await sendStatement(adminKey, claimId, file, note.trim() || undefined);
    setBusy(false);
    if (!r.ok) return onDone(t.failed);
    // The server reports whether the provider ACCEPTED it, not whether a
    // request was made. An operator told "sent" about a message that
    // bounced will sit waiting for a reply that cannot come.
    onDone(r.data.sent ? t.statementSent(r.data.to) : t.failed);
    setFile(null);
    setNote("");
  }

  return (
    <section className={s.section}>
      <h2 className={s.sectionTitle}>{t.statementTitle}</h2>

      {/* A drop zone that is also a real <label> wrapping a real file
          input. Drag-and-drop alone excludes anyone using a keyboard, and
          a styled div that merely looks droppable is the most common way
          an upload becomes unreachable. */}
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
        <span className={s.dropText}>
          {file ? file.name : t.dropHere}
        </span>
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
        className={s.primary}
        disabled={!file || busy}
        onClick={() => void send()}
      >
        {busy ? t.sending : t.sendStatement}
      </button>
    </section>
  );
}

function RequestItems({
  adminKey,
  claimId,
  onDone,
}: {
  adminKey: string;
  claimId: string;
  onDone: (message: string) => void;
}) {
  const t = strings.admin.outreach;
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  async function send() {
    if (!chosen.size) return;
    if (!window.confirm(t.confirmRequest)) return;
    setBusy(true);
    const r = await requestItems(adminKey, claimId, [...chosen], note.trim() || undefined);
    setBusy(false);
    if (!r.ok) return onDone(t.failed);
    onDone(r.data.sent ? t.requestSent(r.data.to) : t.failed);
    setChosen(new Set());
    setNote("");
  }

  return (
    <section className={s.section}>
      <h2 className={s.sectionTitle}>{t.requestTitle}</h2>
      <p className={s.note} style={{ marginBottom: "0.75rem" }}>
        {t.requestLead}
      </p>

      {/* A fixed list, not a text box. These are the same handful of
          things every time, the customer gets a clean checklist instead
          of a sentence typed in a hurry, and we can later count which
          item actually stalls claims. */}
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
        className={s.primary}
        disabled={!chosen.size || busy}
        onClick={() => void send()}
      >
        {busy ? t.sending : t.sendRequest}
      </button>
    </section>
  );
}
