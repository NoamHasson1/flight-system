import type { Metadata, Viewport } from "next";
import { Inter, Plus_Jakarta_Sans } from "next/font/google";

import "./globals.css";

/**
 * Inter, with the system stack behind it.
 *
 * The skill's advice is to default to the platform font, which already ships
 * optical sizing and legibility tuning. The reason to override it here: this
 * interface shows amounts and flight numbers in columns, and Inter's tabular
 * figures are dependable across every platform where San Francisco is not
 * available. `display: swap` means the system font renders immediately and is
 * replaced when Inter arrives, rather than leaving the page blank.
 */
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

/**
 * The display face.
 *
 * Plus Jakarta Sans: rounded, geometric and warm at large sizes, which is the
 * character the Gyro reference gets from its headline face. Used only for
 * display and title -- Inter stays on everything working, because it is more
 * legible small and its tabular figures keep columns of money aligned.
 */
const jakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-jakarta",
  display: "swap",
  weight: ["600", "700", "800"],
});

export const metadata: Metadata = {
  title: "Flight Compensation — are you owed money?",
  description:
    "Check whether a delayed or cancelled flight entitles you to compensation " +
    "under EC261, UK261 or the Israeli Aviation Services Law.",
};

export const viewport: Viewport = {
  // No maximum-scale and no user-scalable=no. Blocking pinch-zoom is one of the
  // most common accessibility mistakes on the web, and this page asks people to
  // read numbers that decide whether they get money.
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#faf9fd" },
    { media: "(prefers-color-scheme: dark)", color: "#14121f" },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${inter.variable} ${jakarta.variable}`}>
      <body>{children}</body>
    </html>
  );
}
