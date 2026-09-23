import type { Metadata } from "next";

import { Faq } from "@/components/Faq";
import { Reveal } from "@/components/Reveal";
import { SiteFooter } from "@/components/SiteFooter";
import { PageHead } from "@/components/PageHead";
import { strings } from "@/lib/strings";

export const metadata: Metadata = {
  title: "שאלות נפוצות על פיצוי טיסה | Skyclaim",
  description:
    "האם מגיע לי פיצוי? כמה? גם לילדים? מה אם חברת התעופה כבר דחתה אותי? " +
    "התשובות לשאלות שנוסעים באמת שואלים.",
};

export default function FaqPage() {
  return (
    <>
      <Reveal />
      <PageHead
        eyebrow={strings.nav.faq}
        title={strings.faq.title}
        lead={strings.faq.pageLead}
      />
      <Faq hideTitle />
      <SiteFooter />
    </>
  );
}
