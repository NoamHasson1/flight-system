"""The emails themselves.

Kept in one file for the same reason the frontend keeps its copy in one file:
tone drifts when it is scattered, and this product writes to people at a moment
when something has already gone wrong for them. The rules are the same as
everywhere else — plain words over legal ones, never blame the reader, never
claim more certainty than we have.

Two things shape every message here.

**The subject line carries the information.** Many people never open the mail;
they read the subject in a list and act on it. "Your claim FS-2026-K7M9QX is
with us" tells them what happened. "Thanks for your submission" tells them
nothing and gets archived.

**Nothing important lives only in the HTML.** The reference, the amount and the
link are all in the plain-text part, because a client that blocks HTML must not
leave someone holding an empty email about their money.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.email.base import EmailMessage

BRAND = "Skyclaim"

# Inlined, because email clients strip <style> blocks and none of them support
# a stylesheet. These are the brand's six colours and nothing else.
_INK = "#111820"
_SLATE = "#5B6470"
_TEAL = "#149F98"
_MIST = "#F5F7F8"
_LINE = "#E6EAED"


def claim_submitted(
    *,
    to: str,
    contact_name: str,
    reference: str,
    flight_number: str,
    route: str,
    amount: str | None,
    passenger_count: int,
    claim_url: str | None = None,
) -> EmailMessage:
    """The one email that genuinely has to arrive.

    Somebody has just handed over their passengers' identity numbers and their
    receipts, and the only thing they have to show for it is a reference on a
    screen they are about to close. This is the receipt.
    """
    money = (
        f"{amount} per passenger"
        if amount and passenger_count == 1
        else f"{amount} per passenger, for {passenger_count} passengers"
        if amount
        else "your compensation"
    )

    text = f"""Hello {contact_name},

Your claim is with us.

  Reference   {reference}
  Flight      {flight_number} · {route}
  Claiming    {money}

Keep that reference. It is how you or we find this claim later, and it is
worth quoting in anything you send the airline yourself.

What happens next
  1. We put the claim to the airline in writing, citing the rule that applies.
  2. Airlines usually reply within a few weeks, sometimes longer.
  3. We email you when there is news — including if the answer is no.

You do not need to do anything else for now. If you find another receipt,
reply to this email and we will add it.

— {BRAND}

This is an automated estimate, not legal advice.
"""

    rows = "".join(
        _row(label, value)
        for label, value in (
            ("Reference", f'<strong style="letter-spacing:.02em">{reference}</strong>'),
            ("Flight", f"{flight_number} &middot; {route}"),
            ("Claiming", money),
        )
    )

    steps = "".join(
        f'<tr><td style="padding:0 0 12px 0;color:{_SLATE};font-size:15px;'
        f'line-height:1.55">'
        f'<span style="display:inline-block;width:22px;height:22px;'
        f"border-radius:11px;background:{_TEAL};color:#fff;text-align:center;"
        f'line-height:22px;font-size:12px;font-weight:700;margin-right:10px">'
        f"{i}</span>{step}</td></tr>"
        for i, step in enumerate(
            (
                "We put the claim to the airline in writing, citing the rule that applies.",
                "Airlines usually reply within a few weeks, sometimes longer.",
                "We email you when there is news &mdash; including if the answer is no.",
            ),
            start=1,
        )
    )

    html = _shell(
        title="Your claim is with us",
        body=f"""
        <p style="margin:0 0 20px;color:{_SLATE};font-size:16px;line-height:1.6">
          Hello {contact_name}, we have your claim.
        </p>

        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
               style="background:{_MIST};border:1px solid {_LINE};border-radius:12px;
                      padding:20px 22px;margin:0 0 24px">
          {rows}
        </table>

        <p style="margin:0 0 6px;color:{_INK};font-size:16px;font-weight:600">
          What happens next
        </p>
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
               style="margin:12px 0 24px">{steps}</table>

        <p style="margin:0;color:{_SLATE};font-size:15px;line-height:1.6">
          You don&rsquo;t need to do anything else for now. If you find another
          receipt, reply to this email and we&rsquo;ll add it.
        </p>
        """,
        action=(claim_url, "View your claim") if claim_url else None,
    )

    return EmailMessage(
        to=to,
        subject=f"Your claim {reference} is with us",
        text=text,
        html=html,
    )


def check_result(
    *,
    to: str,
    flight_number: str,
    route: str,
    verdict: str,
    amount: str | None,
    check_url: str,
) -> EmailMessage:
    """The result of a check, when somebody asked to be sent it.

    Only ever sent to an address a person typed in deliberately. A result email
    nobody asked for is spam, however useful we think it is.
    """
    if verdict == "ELIGIBLE" and amount:
        subject = f"{flight_number}: you can claim {amount}"
        headline = "You can claim compensation"
        lead = (
            f"We checked {flight_number} ({route}) and you can claim "
            f"{amount} per passenger on the booking."
        )
        closing = (
            "Nothing happens until you start the claim, and the check itself "
            "costs you nothing."
        )
        action = (check_url, "Start your claim")
    elif verdict == "NEEDS_REVIEW":
        subject = f"{flight_number}: we need to check this by hand"
        headline = "We need to check this by hand"
        lead = (
            f"Something about {flight_number} ({route}) can&rsquo;t be answered "
            f"automatically."
        )
        # Said explicitly, because the alternative reading costs them money.
        closing = "This is not a no. A person will look at it and come back to you."
        action = (check_url, "See your check")
    else:
        subject = f"{flight_number}: this flight doesn't qualify"
        headline = "This flight doesn&rsquo;t qualify"
        lead = (
            f"We checked {flight_number} ({route}). Compensation depends on how "
            f"late the flight actually was and where it flew, and this one falls "
            f"outside those limits."
        )
        closing = (
            "Nothing here is down to anything you did. If you landed later than "
            "we show, reply and we&rsquo;ll check it by hand."
        )
        action = (check_url, "See your check")

    text = f"""{_plain(headline)}

{_plain(lead)}

{_plain(closing)}

See it here: {check_url}

— {BRAND}

This is an automated estimate, not legal advice.
"""

    html = _shell(
        title=_plain(headline),
        body=f"""
        <p style="margin:0 0 16px;color:{_SLATE};font-size:16px;line-height:1.6">{lead}</p>
        {f'<p style="margin:0 0 24px;color:{_INK};font-size:30px;font-weight:700;letter-spacing:-.02em">{amount}</p>' if amount else ""}
        <p style="margin:0;color:{_SLATE};font-size:15px;line-height:1.6">{closing}</p>
        """,
        action=action,
    )

    return EmailMessage(to=to, subject=subject, text=text, html=html)


# --- the shell ---------------------------------------------------------------


def _row(label: str, value: str) -> str:
    return (
        f'<tr><td style="padding:4px 0;color:{_SLATE};font-size:13px;width:92px;'
        f'vertical-align:top">{label}</td>'
        f'<td style="padding:4px 0;color:{_INK};font-size:15px">{value}</td></tr>'
    )


def _shell(*, title: str, body: str, action: tuple[str, str] | None) -> str:
    """One layout for every message.

    Tables and inline styles, because email clients are twenty years behind
    browsers: no flexbox, no grid, no stylesheets, and Outlook still renders
    through Word. A 600px centred table is the thing that works everywhere.
    """
    button = ""
    if action:
        href, label = action
        button = f"""
        <table role="presentation" cellpadding="0" cellspacing="0" style="margin:28px 0 0">
          <tr><td style="border-radius:10px;background:{_TEAL}">
            <a href="{href}"
               style="display:inline-block;padding:14px 26px;color:#ffffff;
                      font-size:16px;font-weight:700;text-decoration:none">{label}</a>
          </td></tr>
        </table>"""

    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title></head>
<body style="margin:0;padding:0;background:{_MIST};
             font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
         style="background:{_MIST};padding:32px 16px">
    <tr><td align="center">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0"
             style="max-width:600px;background:#ffffff;border:1px solid {_LINE};
                    border-radius:16px;padding:36px 32px">
        <tr><td>
          <p style="margin:0 0 26px;color:{_INK};font-size:17px;font-weight:800;
                    letter-spacing:-.01em">{BRAND}</p>
          <h1 style="margin:0 0 18px;color:{_INK};font-size:26px;line-height:1.2;
                     letter-spacing:-.02em;font-weight:700">{title}</h1>
          {body}
          {button}
        </td></tr>
      </table>
      <p style="margin:20px 0 0;color:{_SLATE};font-size:12px;line-height:1.5;
                max-width:600px">
        This is an automated estimate, not legal advice.
      </p>
    </td></tr>
  </table>
</body></html>"""


def _plain(html: str) -> str:
    """Strip the few entities the copy above uses, for the text part."""
    return (
        html.replace("&rsquo;", "’")
        .replace("&mdash;", "—")
        .replace("&middot;", "·")
        .replace("&amp;", "&")
    )


# --- What the company sees ---------------------------------------------------
#
# A different reader from everything above. Not a customer deciding whether
# they have a claim, but whoever runs this deciding what to do today -- and
# doing it from an inbox rather than from a database, because the person who
# chases an airline is not the person who writes SQL.
#
# Two rules follow from that.
#
# THE SUBJECT LINE IS THE INDEX. It carries the verdict, the amount, the flight
# and the name, in that order, because a mailbox is read as a list of subjects
# and sorted and searched by them. "New claim" tells nobody anything.
#
# THE BODY IS SELF-CONTAINED. Everything needed to act is in the message:
# passengers, expenses, what the airline said, the reference to quote. Nobody
# should have to open the system to understand what arrived.


def ops_check_recorded(
    *,
    to: str,
    flight_number: str,
    flight_date: str,
    route: str | None,
    verdict: str | None,
    status: str,
    amount: str | None,
    regulation: str | None,
    reason: str | None,
    check_url: str,
) -> EmailMessage:
    """Somebody checked a flight. One line of history, filed."""
    headline = _verdict_headline(verdict, status, amount, regulation)
    subject = f"[{BRAND}] {headline} · {flight_number} {flight_date}"

    rows = [
        _row("Flight", f"{flight_number} &middot; {flight_date}"),
        _row("Route", route or "not identified"),
        _row("Result", headline),
    ]
    if reason:
        rows.append(_row("Why", reason))

    body = (
        f'<table role="presentation" cellpadding="0" cellspacing="0" '
        f'style="width:100%;margin:0 0 8px">{"".join(rows)}</table>'
        f'<p style="margin:20px 0 0;color:{_SLATE};font-size:13px;line-height:1.6">'
        f"No action needed unless the result looks wrong. Nobody has left "
        f"their details at this point &mdash; they are only asked for those if "
        f"they go on to claim.</p>"
    )
    html = _shell(title=headline, body=body, action=(check_url, "Open this check"))
    return EmailMessage(to=to, subject=subject, html=html, text=_plain(_as_text(
        [("Flight", f"{flight_number} · {flight_date}"),
         ("Route", route or "not identified"),
         ("Result", headline)]
        + ([("Why", reason)] if reason else []),
        footer=f"Open this check: {check_url}",
    )))


def ops_claim_submitted(
    *,
    to: str,
    reference: str,
    contact_name: str,
    contact_email: str,
    contact_phone: str | None,
    flight_number: str,
    flight_date: str,
    route: str | None,
    verdict: str | None,
    amount: str | None,
    regulation: str | None,
    passengers: Sequence[tuple[str, bool]],
    expenses: Sequence[tuple[str, str]],
    documents: Sequence[str],
    booking_reference: str | None,
    airline_reason: str | None,
    cancellation_notice: str | None,
    claim_url: str,
) -> EmailMessage:
    """Somebody finished a claim. This one is work to be done.

    Identity numbers are deliberately absent. They are encrypted at rest for a
    reason, and copying them into an inbox -- unencrypted, forwarded, backed up
    by a mail provider, searchable forever -- would undo that in one line. The
    count is here so it is obvious they were collected; the numbers stay in the
    system.
    """
    money = f" {amount}" if amount else ""
    subject = (
        f"[{BRAND}] CLAIM{money} &middot; {flight_number} {flight_date} "
        f"&middot; {contact_name}"
    ).replace("&middot;", "·")

    people = "<br>".join(
        f"{name}{' (minor)' if minor else ''}" for name, minor in passengers
    ) or "none listed"
    costs = "<br>".join(f"{what} &mdash; {how_much}" for what, how_much in expenses)
    docs = "<br>".join(documents)

    rows = [
        _row("Reference", f"<strong>{reference}</strong>"),
        _row("Claim for", f"{amount or 'amount not established'}"
             + (f" under {regulation}" if regulation else "")),
        _row("Flight", f"{flight_number} &middot; {flight_date}"
             + (f" &middot; {route}" if route else "")),
        _row("Verdict", verdict or "not decided"),
        _row("Contact", f"{contact_name}<br>{contact_email}"
             + (f"<br>{contact_phone}" if contact_phone else "")),
        _row(f"Passengers ({len(passengers)})", people),
    ]
    if booking_reference:
        rows.append(_row("Booking", booking_reference))
    if cancellation_notice:
        rows.append(_row("Notice", _NOTICE_WORDS.get(
            cancellation_notice, cancellation_notice)))
    if airline_reason:
        rows.append(_row("Airline said", airline_reason))
    rows.append(_row(f"Expenses ({len(expenses)})", costs or "none claimed"))
    rows.append(_row(f"Documents ({len(documents)})", docs or "none uploaded"))

    body = (
        f'<table role="presentation" cellpadding="0" cellspacing="0" '
        f'style="width:100%;margin:0 0 8px">{"".join(rows)}</table>'
    )
    html = _shell(
        title=f"New claim &middot; {amount or 'amount to confirm'}",
        body=body,
        action=(claim_url, "Open this claim"),
    )

    text_rows: list[tuple[str, str]] = [
        ("Reference", reference),
        ("Claim for", (amount or "amount not established")
         + (f" under {regulation}" if regulation else "")),
        ("Flight", f"{flight_number} · {flight_date}" + (f" · {route}" if route else "")),
        ("Verdict", verdict or "not decided"),
        ("Contact", f"{contact_name}, {contact_email}"
         + (f", {contact_phone}" if contact_phone else "")),
        (f"Passengers ({len(passengers)})",
         ", ".join(f"{n}{' (minor)' if m else ''}" for n, m in passengers) or "none"),
    ]
    if booking_reference:
        text_rows.append(("Booking", booking_reference))
    if cancellation_notice:
        text_rows.append(("Notice", _NOTICE_WORDS.get(
            cancellation_notice, cancellation_notice)))
    if airline_reason:
        text_rows.append(("Airline said", airline_reason))
    text_rows.append((f"Expenses ({len(expenses)})",
                      "; ".join(f"{w} — {h}" for w, h in expenses) or "none claimed"))
    text_rows.append((f"Documents ({len(documents)})",
                      "; ".join(documents) or "none uploaded"))

    return EmailMessage(
        to=to,
        subject=subject,
        html=html,
        text=_plain(_as_text(text_rows, footer=f"Open this claim: {claim_url}")),
    )


# Plain words, because "ONE_TO_TWO_WEEKS" is a database value and this is read
# by somebody deciding whether an airline's exemption holds.
_NOTICE_WORDS = {
    "NEVER_TOLD": "never told",
    "ON_THE_DAY": "on the day of the flight",
    "UNDER_A_WEEK": "less than a week before",
    "ONE_TO_TWO_WEEKS": "one to two weeks before",
    "OVER_TWO_WEEKS": "more than two weeks before — the airline may be exempt",
    "CANNOT_REMEMBER": "cannot remember",
}


def _verdict_headline(
    verdict: str | None, status: str, amount: str | None, regulation: str | None
) -> str:
    """The subject line's first words, which is what gets read and sorted."""
    if status == "NOT_FOUND":
        return "Flight not found"
    if status == "AMBIGUOUS":
        return "Several flights matched"
    if verdict == "ELIGIBLE":
        return f"ELIGIBLE {amount}" + (f" ({regulation})" if regulation else "")
    if verdict == "LIKELY_ELIGIBLE":
        return f"Likely {amount}" + (f" ({regulation})" if regulation else "")
    if verdict == "NEEDS_REVIEW":
        return "Needs a person"
    if verdict == "NOT_ELIGIBLE":
        return "Not eligible"
    return "Checked"


def _as_text(rows: Sequence[tuple[str, str]], *, footer: str) -> str:
    width = max((len(label) for label, _ in rows), default=0)
    lines = [f"{label.ljust(width)}  {value}" for label, value in rows]
    return "\n".join(lines) + f"\n\n{footer}\n"
