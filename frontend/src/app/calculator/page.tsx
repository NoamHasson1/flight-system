import type { Metadata } from "next";

import { Calculator } from "@/components/Calculator";
import { PageHead } from "@/components/PageHead";
import { Reveal } from "@/components/Reveal";
import { SiteFooter } from "@/components/SiteFooter";
import { resolveBackendOrigin } from "@/lib/backend-origin";
import { strings } from "@/lib/strings";

export const metadata: Metadata = {
  title: "מחשבון פיצוי טיסה — כמה מגיע לכם? | Skyclaim",
  description:
    "מחשבון פיצוי לטיסה שבוטלה או התעכבה. בחרו יעד, מה קרה וכמה נוסעים " +
    "הייתם — וקבלו הערכה לפי החוק הישראלי, האירופי והבריטי.",
};

/**
 * RENDERED PER REQUEST, NOT AT BUILD TIME.
 *
 * `revalidate` alone makes this a static page generated during `next build`.
 * That build runs in its own container, where the backend does not exist --
 * so the fetch below fails, the fallback renders an empty page, and the
 * EMPTY page is what gets cached and shipped. Not a risk: a certainty, and a
 * silent one, because the build succeeds and the page returns 200.
 *
 * Caught here by the figures being missing locally. The same thing would have
 * reached production looking exactly like a page nobody had finished.
 *
 * Per-request costs a few milliseconds -- the backend is on the private
 * network -- and means the page is right whenever the backend is up, and
 * degrades to its heading when it is not.
 */
export const dynamic = "force-dynamic";

export default async function CalculatorPage() {
  const c = strings.calculator;
  let regulations = [];
  try {
    const response = await fetch(
      `${resolveBackendOrigin(process.env.BACKEND_ORIGIN)}/api/v1/regulations`,
      { cache: "no-store" },
    );
    if (response.ok) regulations = (await response.json()).regulations;
  } catch {
    // A calculator with no figures is not a calculator. Rather than render an
    // empty one, the page shows its heading and the link to the real check --
    // which is where somebody was going to end up anyway.
  }

  return (
    <>
      <Reveal />
      <PageHead eyebrow={c.eyebrow} title={c.title} lead={c.lead} />
      {regulations.length > 0 ? <Calculator regulations={regulations} /> : null}
      <SiteFooter />
    </>
  );
}
