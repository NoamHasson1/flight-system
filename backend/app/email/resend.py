"""Resend adapter -- email over HTTPS, because SMTP is blocked.

WHY THIS EXISTS
---------------
Managed hosts close the outbound SMTP ports. Render, Fly, most of Heroku's
successors: 25, 465 and 587 are shut, because a rented container that can open
an SMTP connection is a spam relay waiting to be found. The symptom is exact
and unhelpful:

    could not send email (OSError): [Errno 101] Network is unreachable

Nothing to do with credentials. A correct Gmail app password, correct host,
correct port, and the connection never leaves the container.

Port 443 is open, so the answer is a provider with an HTTP API. That is this
file. Nothing above the `EmailSender` port changes -- which is the point of
having had the port.

ONE THING TO KNOW BEFORE THE FIRST SEND
---------------------------------------
Resend will only send FROM a domain you have verified. Until then it gives you
`onboarding@resend.dev`, which may only send TO the address the Resend account
was registered with.

That is enough for the company's own notifications, and not enough for
customer confirmations -- those go to whichever address the customer typed,
and will be refused. Verifying a domain lifts both limits, and is the point at
which this stops being a demonstration.

The refusal is logged with the provider's own words rather than swallowed,
because "why did that one customer not get their confirmation" is otherwise
unanswerable.
"""

from __future__ import annotations

import base64
import logging
from typing import Final

import httpx

from app.email.base import EmailMessage

logger = logging.getLogger("flight_system.email")

DEFAULT_ENDPOINT: Final = "https://api.resend.com/emails"

# Short. The send happens in a background task after the response has gone, so
# nobody is waiting -- but a request that hangs holds a worker, and a mail
# provider that has not answered in fifteen seconds is not about to.
DEFAULT_TIMEOUT: Final = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)


class ResendEmailSender:
    """Sends through Resend's HTTP API. Satisfies `EmailSender`."""

    name = "resend"

    def __init__(
        self,
        api_key: str,
        sender: str,
        *,
        endpoint: str = DEFAULT_ENDPOINT,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            # Fail here rather than on the first send. A missing key that only
            # surfaces when somebody files a claim is a missing key nobody
            # notices until it has already cost something.
            raise ValueError(
                "resend: no API key configured. Set RESEND_API_KEY, or select "
                "the 'console' sender to run without one."
            )
        self._api_key = api_key.strip()
        self._sender = sender
        self._endpoint = endpoint
        self._client = client

    def send(self, message: EmailMessage) -> bool:
        """True if the provider accepted it. Never raises.

        A failed email must not fail the thing it was reporting on: somebody
        who files a claim and sees an error will assume it did not go through,
        and will either give up or file it twice. The claim is the valuable
        thing; the email is a courtesy.
        """
        payload = {
            "from": self._sender,
            "to": [message.to],
            "subject": message.subject,
            "text": message.text,
            "html": message.html,
        }
        if message.reply_to:
            payload["reply_to"] = [message.reply_to]

        # Base64, which is what the API takes. It inflates the bytes by about
        # a third, so the guard in `notify_ops_claim` budgets against the
        # ENCODED size rather than the file size.
        if message.attachments:
            payload["attachments"] = [
                {
                    "filename": a.filename,
                    "content": base64.b64encode(a.content).decode("ascii"),
                    "content_type": a.content_type,
                }
                for a in message.attachments
            ]

        try:
            response = self._post(payload)
        except httpx.HTTPError as exc:
            logger.error("could not reach Resend for %s (%s)", message.to, exc)
            return False

        if response.status_code < 300:
            logger.info(
                "sent %r to %s%s",
                message.subject,
                message.to,
                f" with {len(message.attachments)} attachment(s)"
                if message.attachments
                else "",
            )
            return True

        # The provider's own words, not ours. The two refusals that actually
        # happen -- an unverified sending domain, and a free account that may
        # only write to its owner -- are both explained clearly by Resend and
        # not at all by a status code.
        logger.error(
            "Resend refused mail to %s (%s): %s",
            message.to,
            response.status_code,
            _detail(response),
        )
        return False

    def _post(self, payload: dict[str, object]) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if self._client is not None:
            return self._client.post(self._endpoint, json=payload, headers=headers)
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            return client.post(self._endpoint, json=payload, headers=headers)


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(body, dict):
        return str(body.get("message") or body.get("error") or body)[:200]
    return str(body)[:200]
