import Link from "next/link";

import { strings } from "@/lib/strings";

import s from "./hero.module.css";

/**
 * The Google rating, as a badge that links to the source.
 *
 * WHY LINKED, AND WHY THE STARS ARE NOT OURS TO INVENT
 * ----------------------------------------------------
 * A five-star row printed on a company's own website is worth almost nothing:
 * the company drew it. The same five stars next to a link to the listing are
 * worth a great deal, because anybody can click and find out in one second.
 *
 * So this always links out, and it says which profile it came from. The value
 * is in the verifiability, not in the stars.
 *
 * REVIEW TEXT IS DELIBERATELY ABSENT
 * ----------------------------------
 * Copying review text off the listing would be a terms violation and -- more
 * to the point -- it would be text we could quietly edit, which is precisely
 * what makes testimonials on a company's own site unpersuasive. The Places
 * API returns reviews with attribution under terms that allow displaying
 * them; until that is wired up, the rating and the link do the job honestly.
 */
export function GoogleRating({ tone = "light" }: { tone?: "light" | "ink" }) {
  const r = strings.reviews;
  const dim = tone === "ink" ? "var(--text-on-ink-dim)" : "var(--text-muted)";
  const strong = tone === "ink" ? "var(--text-on-ink)" : "var(--text-strong)";

  return (
    <Link
      href={r.url}
      target="_blank"
      rel="noopener noreferrer"
      className={`${s.ratingBadge} press`}
      aria-label={`${r.rating} ${r.ratingLabel}, ${r.count} ${r.countLabel} — ${r.readAll}`}
    >
      <GoogleMark />
      <span className={`${s.code} text-heading`} style={{ color: strong }}>
        {r.rating}
      </span>
      <Stars />
      <span className="text-callout" style={{ color: dim }}>
        {r.count} {r.countLabel}
      </span>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden style={{ color: dim }}>
        <path d="M7 17 17 7M9 7h8v8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </Link>
  );
}

/** Five filled stars. `aria-hidden` because the label above already says the
    rating in words — a screen reader does not need "star star star". */
function Stars() {
  return (
    <span className="flex gap-0.5" aria-hidden>
      {[0, 1, 2, 3, 4].map((i) => (
        <svg key={i} width="15" height="15" viewBox="0 0 24 24" fill="#f5b544">
          <path d="m12 2 3 6.6 7 .9-5.1 4.9 1.3 7-6.2-3.4L5.8 21.4l1.3-7L2 9.5l7-.9L12 2Z" />
        </svg>
      ))}
    </span>
  );
}

function GoogleMark() {
  return (
    <svg width="17" height="17" viewBox="0 0 48 48" aria-hidden>
      <path fill="#4285F4" d="M45.1 24.5c0-1.6-.1-2.8-.4-4H24v7.3h12.1c-.2 2-1.6 5-4.5 7l-.1.3 6.5 5 .5.1c4.1-3.8 6.6-9.4 6.6-15.7Z" />
      <path fill="#34A853" d="M24 46c5.9 0 10.9-1.9 14.5-5.3l-6.9-5.4c-1.8 1.3-4.3 2.2-7.6 2.2-5.8 0-10.7-3.8-12.5-9.1l-.3.02-6.7 5.2-.1.3C8 41.6 15.4 46 24 46Z" />
      <path fill="#FBBC05" d="M11.5 28.4c-.5-1.4-.7-2.9-.7-4.4s.3-3 .7-4.4v-.3l-6.8-5.3-.2.1A22 22 0 0 0 2 24c0 3.5.9 6.9 2.5 9.9l7-5.5Z" />
      <path fill="#EA4335" d="M24 10.5c4.1 0 6.9 1.8 8.5 3.3l6.2-6C34.9 4.4 29.9 2 24 2 15.4 2 8 6.4 4.5 14.1l7 5.5c1.8-5.3 6.7-9.1 12.5-9.1Z" />
    </svg>
  );
}
