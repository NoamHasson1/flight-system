import type { Metadata } from "next";

import { FlightBoard } from "@/components/Board";
import { Reveal } from "@/components/Reveal";
import { SiteFooter } from "@/components/SiteFooter";
import { PageHead } from "@/components/PageHead";
import { strings } from "@/lib/strings";

export const metadata: Metadata = {
  title: "לוח שיבושי טיסות בנתב״ג — ביטולים ועיכובים | Skyclaim",
  description:
    "טיסות שבוטלו או התעכבו לאחרונה בנתב״ג, עם הפיצוי שעשוי להגיע על כל " +
    "אחת. הנתונים מגיעים מלוח הטיסות הרשמי.",
};

export default function BoardPage() {
  const b = strings.board;
  return (
    <>
      <Reveal />
      <PageHead eyebrow={strings.nav.board} title={b.title} lead={b.pageLead} />
      {/* The same component the landing page uses. One board, one set of
          rules about what it shows, and no chance of the two drifting. */}
      <FlightBoard />
      <SiteFooter />
    </>
  );
}
