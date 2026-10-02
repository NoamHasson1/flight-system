/**
 * The operator console's own layout.
 *
 * It exists for the metadata. `page.tsx` is a client component -- it has to
 * be, since it reads the key from sessionStorage and fetches every row in
 * the browser -- and a client component cannot export `metadata`, so the
 * page would otherwise inherit the marketing title and sit in search
 * results as "Skyclaim — compensation for cancelled flights".
 *
 * `noindex, nofollow` matters more than the title. The page itself holds no
 * data without a key, but a crawler finding it, indexing it and listing it
 * next to the public site invites people to try the door. Nothing here is
 * for the public.
 */

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "לקוחות · Skyclaim",
  robots: { index: false, follow: false },
};

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
