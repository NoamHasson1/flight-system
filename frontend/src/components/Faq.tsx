"use client";

import { useState } from "react";

import { strings } from "@/lib/strings";

import s from "./hero.module.css";

/**
 * The questions people actually ask.
 *
 * An accordion rather than a wall of text: every answer here begins with a
 * hedge -- "not necessarily", "it depends" -- because the honest answer to
 * most of these is that it depends on the specific flight. Ten hedged
 * paragraphs in a row read as evasion. Ten questions with the hedge one click
 * away reads as a list of things we will check for you.
 *
 * Built on <details>/<summary> semantics via buttons and aria-expanded so it
 * is keyboard-operable and announced correctly, rather than a div that
 * happens to toggle a class.
 */
export function Faq({ hideTitle = false }: { hideTitle?: boolean } = {}) {
  const [open, setOpen] = useState<number | null>(0);
  const f = strings.faq;

  return (
    <section id="faq" className={`${s.mist} px-5 py-20 sm:px-8 sm:py-24`}>
      <div className="mx-auto max-w-3xl">
        {hideTitle ? null : (
          <h2 className="text-title" style={{ color: "var(--text-strong)" }}>
            {f.title}
          </h2>
        )}

        <div className={hideTitle ? "" : "mt-8"}>
          {f.items.map((item, i) => {
            const isOpen = open === i;
            return (
              <div key={item.q} className={`${s.faqItem} ${isOpen ? s.faqOpen : ""}`}>
                <button
                  type="button"
                  className={`${s.faqQ} text-subhead`}
                  aria-expanded={isOpen}
                  aria-controls={`faq-a-${i}`}
                  onClick={() => setOpen(isOpen ? null : i)}
                >
                  <span>{item.q}</span>
                  <span className={s.faqMark} aria-hidden>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                      <path
                        d="M12 5v14M5 12h14"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                      />
                    </svg>
                  </span>
                </button>
                <div
                  id={`faq-a-${i}`}
                  className={s.faqA}
                  style={{
                    maxHeight: isOpen ? "22rem" : 0,
                    opacity: isOpen ? 1 : 0,
                    paddingBottom: isOpen ? "1.25rem" : 0,
                    transition:
                      "max-height var(--duration-base) var(--ease-out-soft), " +
                      "opacity var(--duration-quick) var(--ease-out-soft), " +
                      "padding var(--duration-base) var(--ease-out-soft)",
                  }}
                >
                  {item.a}
                </div>
              </div>
            );
          })}
        </div>

        <p className="mt-10 text-callout" style={{ color: "var(--text-muted)" }}>
          {f.more}
        </p>
      </div>
    </section>
  );
}
