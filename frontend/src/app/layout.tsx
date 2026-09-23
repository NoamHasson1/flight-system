import type { Metadata, Viewport } from "next";
import { Heebo, JetBrains_Mono } from "next/font/google";

import { SiteNav } from "@/components/SiteNav";

import "./globals.css";

/**
 * Heebo, the working face.
 *
 * This interface is Hebrew, and a Latin face with a Hebrew fallback is not the
 * same thing as a Hebrew face: the fallback differs by platform, so the same
 * page has different letterforms, weights and line heights on every machine.
 * Heebo is drawn for both scripts by the same hand -- it is Roboto's Latin
 * matched to a Hebrew companion -- so a sentence mixing "LY315" with Hebrew
 * words does not change typeface halfway through.
 *
 * `display: swap` means the system font renders immediately and is replaced
 * when Heebo arrives, rather than leaving the page blank.
 */
const heebo = Heebo({
  subsets: ["hebrew", "latin"],
  variable: "--font-heebo",
  display: "swap",
  weight: ["400", "500", "700", "900"],
});

/**
 * The monospace face, for the things that are codes rather than words.
 *
 * Flight numbers and amounts are read as SHAPES down a column -- LY315 under
 * BZ746, 1,530 under 3,670 -- and a proportional face makes the column ragged
 * and the comparison slow. It is also the one place Latin belongs in a Hebrew
 * page: a flight number is not a Hebrew word and pretending otherwise makes
 * the direction ambiguous.
 */
const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
  weight: ["400", "500", "700"],
});

export const metadata: Metadata = {
  title: 'Skyclaim — פיצוי על טיסות שבוטלו או התעכבו | עו"ד יצחק מימון',
  description:
    "הטיסה בוטלה או התעכבה? בדקו תוך פחות מדקה כמה פיצוי עשוי להגיע לכם " +
    "לפי חוק שירותי תעופה, EU261 ו-UK261. בדיקה חינם, בלי הרשמה.",
};

export const viewport: Viewport = {
  // No maximum-scale and no user-scalable=no. Blocking pinch-zoom is one of the
  // most common accessibility mistakes on the web, and this page asks people to
  // read numbers that decide whether they get money.
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f5f7f9" },
    { media: "(prefers-color-scheme: dark)", color: "#151a22" },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    // dir="rtl" on the ROOT, not on a wrapper. Every layout below it then
    // inherits direction, so `margin-inline-start` means "before the text"
    // everywhere and nothing has to know which way the page runs. Setting it
    // lower down leaves the scrollbar, the focus order and native form
    // controls on the wrong side.
    <html lang="he" dir="rtl" className={`${heebo.variable} ${mono.variable}`}>
      <body>
        {/* One nav for the whole site, so a new page cannot ship without it
            and the current tab is known from the route rather than passed in
            by every page. */}
        <SiteNav />
        {children}
      </body>
    </html>
  );
}
