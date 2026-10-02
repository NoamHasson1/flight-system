/**
 * The archive screen's own title.
 *
 * Without this it inherits "לקוחות · Skyclaim" from the parent admin
 * layout, which is wrong in the one place a title is actually used: an
 * operator with both screens open in two tabs cannot tell them apart.
 *
 * `noindex` is inherited from the parent and does not need restating.
 */

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "ארכיון טיסות · Skyclaim",
};

export default function FlightsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
