/**
 * Showing a customer's files, not just offering to download them.
 *
 * WHY THIS IS MORE THAN AN <img src>
 *
 * The bytes are behind the admin key, and the key travels in a header so
 * it never lands in a URL, a server log or browser history. A browser
 * cannot put a header on an `<img src>`, so each file is fetched here and
 * handed to the DOM as a blob URL.
 *
 * That has a cost worth naming: every blob URL is a live handle to a
 * customer's passport or receipt, held in the tab until it is revoked.
 * This component revokes every one it created when it unmounts, so closing
 * the panel really does let go of the documents.
 *
 * Non-images -- a PDF booking confirmation, mostly -- get a row with a
 * download rather than a broken thumbnail. Pretending to preview something
 * we cannot render is worse than saying so.
 */

"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { documentObjectUrl, downloadDocument, type CustomerDetail } from "@/lib/api";
import { strings } from "@/lib/strings";
import s from "./crm.module.css";

type Doc = CustomerDetail["documents"][number];

const isImage = (d: Doc) => d.content_type.startsWith("image/");

export function Files({
  adminKey,
  documents,
}: {
  adminKey: string;
  documents: Doc[];
}) {
  const t = strings.admin;
  const [urls, setUrls] = useState<Record<string, string>>({});
  /**
   * Why a thumbnail has no image.
   *
   * Without this the tile said "loading" forever when a fetch failed --
   * which is exactly what happened to every file uploaded before the
   * backend got a persistent disk. A spinner that never resolves is the
   * worst possible report of a permanent failure: the operator waits,
   * reloads, waits again, and never learns that the bytes are gone and
   * the customer needs to be asked for them again.
   */
  const [failures, setFailures] = useState<Record<string, "gone" | "error">>({});
  const [lightbox, setLightbox] = useState<number | null>(null);
  // Held in a ref as well as state: the cleanup runs after the last render
  // and needs the final set, not the one captured when the effect ran.
  const created = useRef<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      for (const doc of documents.filter(isImage)) {
        const result = await documentObjectUrl(adminKey, doc.id);
        if (cancelled) {
          // The panel closed mid-fetch. Release immediately rather than
          // leaking one handle per file the operator did not wait for.
          if (result.ok) URL.revokeObjectURL(result.url);
          return;
        }
        if (result.ok) {
          created.current.push(result.url);
          setUrls((prev) => ({ ...prev, [doc.id]: result.url }));
        } else {
          setFailures((prev) => ({ ...prev, [doc.id]: result.reason }));
        }
      }
    })();
    return () => {
      cancelled = true;
      for (const url of created.current) URL.revokeObjectURL(url);
      created.current = [];
    };
  }, [adminKey, documents]);

  const images = documents.filter(isImage);
  const others = documents.filter((d) => !isImage(d));

  return (
    <>
      {images.length > 0 && (
        <div className={s.thumbs}>
          {images.map((doc, i) => (
            <button
              key={doc.id}
              type="button"
              className={s.thumb}
              onClick={() => setLightbox(i)}
              title={doc.original_filename}
            >
              {urls[doc.id] ? (
                /* A blob URL cannot go through next/image, which needs a
                   path it can fetch and optimise on the server. These
                   bytes exist only in this tab and never had a URL. */
                // eslint-disable-next-line @next/next/no-img-element
                <img src={urls[doc.id]} alt={doc.original_filename} />
              ) : failures[doc.id] ? (
                <span className={s.thumbGone}>
                  {failures[doc.id] === "gone"
                    ? t.files.gone
                    : t.files.loadFailed}
                </span>
              ) : (
                <span className={s.thumbLoading}>{t.files.loading}</span>
              )}
              <span className={s.thumbKind}>{t.kinds[doc.kind] ?? doc.kind}</span>
            </button>
          ))}
        </div>
      )}

      {others.map((doc) => (
        <FileRow key={doc.id} adminKey={adminKey} file={doc} />
      ))}

      {lightbox !== null && (
        <Lightbox
          images={images.filter((d) => !failures[d.id])}
          urls={urls}
          index={lightbox}
          onIndex={setLightbox}
          onClose={() => setLightbox(null)}
          adminKey={adminKey}
        />
      )}
    </>
  );
}

function Lightbox({
  images,
  urls,
  index,
  onIndex,
  onClose,
  adminKey,
}: {
  images: Doc[];
  urls: Record<string, string>;
  index: number;
  onIndex: (i: number) => void;
  onClose: () => void;
  adminKey: string;
}) {
  const t = strings.admin;
  const doc = images[index];

  // Escape closes, arrows step through. A receipt and a boarding pass are
  // usually looked at together, and reaching for the mouse between each
  // one is the difference between glancing and working.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      // The document is right-to-left, so the LEFT arrow means "onward"
      // the way it does in every Hebrew reader.
      if (e.key === "ArrowLeft") onIndex((index + 1) % images.length);
      if (e.key === "ArrowRight")
        onIndex((index - 1 + images.length) % images.length);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [index, images.length, onClose, onIndex]);

  // PORTALLED TO THE BODY, and it has to be.
  //
  // This component renders inside the detail slide-over, which is itself
  // `position: fixed` with its own scrolling and stacking context. A
  // full-screen overlay declared in there is laid out against the panel
  // rather than the viewport: the first version covered only the strip of
  // page beside the panel, leaving half the screen undimmed and the
  // customer's details still legible behind an "image viewer".
  //
  // A portal moves the node to the end of <body>, where `inset: 0` means
  // what it says.
  return createPortal(
    <div className={s.lightbox} role="dialog" aria-modal="true">
      <div className={s.lightboxBar}>
        <button type="button" className={s.ghost} onClick={onClose}>
          {t.files.close}
        </button>
        <span className={s.lightboxName}>{doc.original_filename}</span>
        <span className={s.spacer} />
        {images.length > 1 && (
          <span className={s.lightboxCount}>
            {t.files.of(index + 1, images.length)}
          </span>
        )}
        <button
          type="button"
          className={s.ghost}
          onClick={() =>
            void downloadDocument(adminKey, doc.id, doc.original_filename)
          }
        >
          {t.files.download}
        </button>
      </div>

      {/* Clicking the backdrop closes; clicking the image does not, so a
          drag to inspect a blurry receipt cannot dismiss it by accident. */}
      <div className={s.lightboxStage} onClick={onClose}>
        {urls[doc.id] ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={urls[doc.id]}
            alt={doc.original_filename}
            onClick={(e) => e.stopPropagation()}
          />
        ) : (
          <span className={s.thumbGone}>{t.files.gone}</span>
        )}
      </div>
    </div>,
    document.body,
  );
}

function FileRow({ adminKey, file }: { adminKey: string; file: Doc }) {
  const t = strings.admin;
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  return (
    <>
      <button
        type="button"
        className={s.file}
        disabled={busy}
        onClick={() => {
          setBusy(true);
          setError(null);
          void downloadDocument(adminKey, file.id, file.original_filename).then(
            (r) => {
              setBusy(false);
              if (!r.ok) {
                setError(
                  r.failure.kind === "refused"
                    ? r.failure.message
                    : strings.errors.unreachable,
                );
              }
            },
          );
        }}
      >
        <span className={s.fileName}>{file.original_filename}</span>
        <span className={s.fileMeta}>
          {t.kinds[file.kind] ?? file.kind} ·{" "}
          {Math.max(1, Math.round(file.size_bytes / 1024))}KB · {t.files.download}
        </span>
      </button>
      {error && <p className={s.error}>{error}</p>}
    </>
  );
}
