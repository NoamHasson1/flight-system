"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { strings } from "@/lib/strings";

import s from "./hero.module.css";

/**
 * The site's navigation.
 *
 * REAL PAGES, NOT ANCHORS
 * -----------------------
 * Each tab is its own route. An anchor to a section on one long page is
 * cheaper to build and worse for everything that matters here: a customer
 * cannot send somebody "the page about the law", the browser's back button
 * does nothing useful, and Google indexes one page instead of six -- which
 * for a service people find by searching "פיצוי על ביטול טיסה" is the whole
 * acquisition channel.
 *
 * WHY IT KNOWS WHERE YOU ARE
 * --------------------------
 * A nav that does not mark the current page makes every page feel like the
 * same page. `aria-current` says it to a screen reader; the underline says it
 * to everyone else.
 *
 * WHY IT CHANGES ON SCROLL
 * ------------------------
 * At the top of a page it is transparent and lets the hero run full height.
 * Once content is passing underneath it becomes glass, so the text does not
 * smear through it. That is Apple's material rule: the bar is a floating
 * layer over content, not a strip cut out of the page.
 */
export function SiteNav() {
  const pathname = usePathname();
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    // Passive: this listener never calls preventDefault, and saying so lets
    // the browser scroll without waiting to find out.
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const n = strings.nav;
  const tabs = [
    { href: "/rights", label: n.rights },
    { href: "/calculator", label: n.calculator },
    { href: "/board", label: n.board },
    { href: "/how", label: n.how },
    { href: "/faq", label: n.faq },
    { href: "/about", label: n.about },
  ];

  return (
    <header
      className={`${s.nav} ${scrolled ? "glass" : ""} px-5 py-3 sm:px-8`}
      style={scrolled ? undefined : { background: "transparent", borderColor: "transparent" }}
    >
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4">
        <Link href="/" className="flex shrink-0 items-center gap-2.5 no-underline">
          <span
            aria-hidden
            className="grid size-8 place-items-center rounded-lg"
            style={{ background: "var(--color-teal-600)", color: "#fff" }}
          >
            <PlaneMark />
          </span>
          <span
            className="text-subhead font-black tracking-wide"
            style={{ color: "var(--text-strong)" }}
          >
            SKYCLAIM
          </span>
        </Link>

        <nav className="hidden items-center gap-6 lg:flex" aria-label={n.aria}>
          {tabs.map((tab) => {
            const here = pathname === tab.href;
            return (
              <Link
                key={tab.href}
                href={tab.href}
                aria-current={here ? "page" : undefined}
                className={`${s.navLink} ${here ? s.navHere : ""} text-callout`}
              >
                {tab.label}
              </Link>
            );
          })}
        </nav>

        <div className="flex items-center gap-2">
          <Link
            href="/#check"
            className={`${s.cta} ${s.ctaPill} press hidden px-5 py-2.5 text-callout sm:inline-flex`}
          >
            {n.cta}
          </Link>
          <button
            type="button"
            className="lg:hidden"
            aria-expanded={open}
            aria-label={n.menu}
            onClick={() => setOpen((v) => !v)}
            style={{ color: "var(--text-strong)" }}
          >
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" aria-hidden>
              {open ? (
                <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              ) : (
                <path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              )}
            </svg>
          </button>
        </div>
      </div>

      {open ? (
        <nav className="mt-3 grid gap-1 lg:hidden" aria-label={n.aria}>
          {tabs.map((tab) => (
            <Link
              key={tab.href}
              href={tab.href}
              aria-current={pathname === tab.href ? "page" : undefined}
              onClick={() => setOpen(false)}
              className="rounded-xl px-4 py-3 text-subhead"
              style={{
                background:
                  pathname === tab.href ? "var(--verdict-yes-fill)" : "transparent",
                color: "var(--text-strong)",
              }}
            >
              {tab.label}
            </Link>
          ))}
          <Link
            href="/#check"
            onClick={() => setOpen(false)}
            className={`${s.cta} ${s.ctaPill} press mt-2 justify-center px-5 py-3 text-subhead`}
          >
            {n.cta}
          </Link>
        </nav>
      ) : null}
    </header>
  );
}

function PlaneMark() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5L21 16Z"
        fill="currentColor"
      />
    </svg>
  );
}
