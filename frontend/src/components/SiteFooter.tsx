import Link from "next/link";

import { strings } from "@/lib/strings";

/**
 * The footer, shared by every page.
 *
 * Its links are REAL routes now that the tabs are pages. A footer full of
 * dead text is a footer that tells a visitor the site is a mock-up.
 */
export function SiteFooter() {
  const f = strings.footer;
  const n = strings.nav;

  const columns = [
    {
      title: "Skyclaim",
      links: [
        { label: n.cta, href: "/#check" },
        { label: n.board, href: "/board" },
        { label: n.calculator, href: "/calculator" },
      ],
    },
    {
      title: "מידע",
      links: [
        { label: n.rights, href: "/rights" },
        { label: n.how, href: "/how" },
        { label: n.faq, href: "/faq" },
      ],
    },
    {
      title: "אודות",
      links: [{ label: n.about, href: "/about" }],
    },
  ];

  return (
    <footer className="px-5 py-14 sm:px-8" style={{ background: "var(--surface-mist)" }}>
      <div className="mx-auto max-w-6xl">
        <div className="grid gap-10 md:grid-cols-4">
          <div>
            <p className="text-subhead font-black" style={{ color: "var(--text-strong)" }}>
              SKYCLAIM
            </p>
            <p className="mt-3 max-w-xs text-callout" style={{ color: "var(--text-muted)" }}>
              {f.blurb}
            </p>
          </div>
          {columns.map((col) => (
            <div key={col.title}>
              <p className="text-callout font-bold" style={{ color: "var(--text-strong)" }}>
                {col.title}
              </p>
              <ul className="mt-3 space-y-2">
                {col.links.map((link) => (
                  <li key={link.href}>
                    <Link
                      href={link.href}
                      className="text-callout no-underline"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-10 border-t pt-6" style={{ borderColor: "var(--border-subtle)" }}>
          <p className="text-caption" style={{ color: "var(--text-muted)" }}>
            {f.rights}
          </p>
          <p className="mt-1 text-caption" style={{ color: "var(--text-muted)" }}>
            {f.disclaimer}
          </p>
        </div>
      </div>
    </footer>
  );
}
