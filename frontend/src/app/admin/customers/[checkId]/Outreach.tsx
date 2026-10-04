/**
 * The two things an operator sends to a customer by hand, as sections on
 * the customer's own page.
 *
 *   THE STATEMENT OF CLAIM   drop the lawyer's pleading in, it goes out
 *   A REQUEST FOR ITEMS      tick what is missing, it goes out
 *
 * THE FORMS THEMSELVES LIVE IN `admin/OutreachForms.tsx`, because the
 * same two are also reachable from a button at the end of each row in
 * the list. This file is only the headings and the frame around them:
 * two copies of a form that sends mail over a lawyer's name would be two
 * places for the wording, the confirmation and the error handling to
 * drift apart.
 */

"use client";

import { RequestItemsForm, StatementForm } from "../../OutreachForms";
import { strings } from "@/lib/strings";
import s from "../../crm.module.css";

export function Outreach({
  adminKey,
  claimId,
  email,
  onDone,
}: {
  adminKey: string;
  claimId: string;
  /** The recipient. Named in the confirmation before anything is sent. */
  email: string;
  onDone: (message: string) => void;
}) {
  const t = strings.admin.outreach;

  return (
    <>
      <section className={s.section}>
        <h2 className={s.sectionTitle}>{t.statementTitle}</h2>
        <StatementForm
          adminKey={adminKey}
          claimId={claimId}
          email={email}
          onDone={onDone}
        />
      </section>

      <section className={s.section}>
        <h2 className={s.sectionTitle}>{t.requestTitle}</h2>
        <RequestItemsForm
          adminKey={adminKey}
          claimId={claimId}
          email={email}
          onDone={onDone}
        />
      </section>
    </>
  );
}
