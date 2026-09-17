"""Where uploaded receipts and bookings actually live.

Local disk for now, behind a narrow interface, so moving to object storage
later is one new class and a line of configuration.

Everything defensive about file uploads is in this file. The rule it exists to
enforce: **nothing the customer sends is ever used to build a path**. Not the
filename, not the extension, not the content type. The customer supplies bytes;
we decide entirely where they go and what we call them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

# What a claim can reasonably consist of: a booking confirmation, a hotel
# invoice, a photograph of a taxi receipt. An allowlist, not a blocklist --
# a blocklist is a list of the attacks somebody already thought of.
ALLOWED_TYPES: Final[dict[str, str]] = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
}

# A phone photograph of a receipt is around 2-5 MB; a scanned multi-page
# booking is rarely more than 10. Generous enough not to reject real evidence,
# small enough that a hundred of them do not fill a disk.
MAX_BYTES: Final = 10 * 1024 * 1024

# The first few bytes of each format we accept. The Content-Type header comes
# from the client and is therefore a claim, not a fact: a browser will happily
# send `application/pdf` for anything at all, and an attacker will send it
# deliberately. Checking the bytes is how we find out what a file actually is.
_SIGNATURES: Final[tuple[tuple[bytes, str], ...]] = (
    (b"%PDF-", "application/pdf"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)

# The formats whose first bytes we can check with confidence. A file declaring
# one of these MUST match its signature.
#
# WebP and HEIC are absent on purpose: both are container formats whose
# signatures need more care than a prefix match, and wrongly rejecting a
# perfectly good phone photo is a worse outcome than accepting one unverified.
VERIFIABLE_TYPES: Final[frozenset[str]] = frozenset(
    content_type for _, content_type in _SIGNATURES
)


class UploadRejected(Exception):
    """The file cannot be stored, for a reason the customer should be told."""


@dataclass(frozen=True, slots=True)
class StoredFile:
    """Where a file went. `path` is opaque to everything but the storage."""

    path: str
    size_bytes: int
    content_type: str


class FileStorage(Protocol):
    def save(self, content: bytes, *, content_type: str) -> StoredFile: ...
    def open(self, path: str) -> bytes: ...
    def delete(self, path: str) -> None: ...


class LocalFileStorage:
    """Files on local disk, under a root directory.

    Paths look like `ab/cd/abcdef…12.pdf`: two levels of sharding by the first
    four characters of a random name. One flat directory with fifty thousand
    receipts in it is slow to list on most filesystems and miserable to back up.
    """

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, content: bytes, *, content_type: str) -> StoredFile:
        declared = (content_type or "").split(";")[0].strip().lower()

        if not content:
            raise UploadRejected("That file is empty.")
        if len(content) > MAX_BYTES:
            raise UploadRejected(
                f"That file is {len(content) / 1_048_576:.1f} MB. The limit is "
                f"{MAX_BYTES // 1_048_576} MB -- try photographing the receipt "
                f"rather than scanning it."
            )
        if declared not in ALLOWED_TYPES:
            raise UploadRejected(
                f"We cannot accept {declared or 'that kind of file'}. Please "
                f"upload a PDF or a photo (JPEG, PNG, WebP or HEIC)."
            )

        if declared in VERIFIABLE_TYPES and _sniff(content) != declared:
            # The file is not what it says it is.
            #
            # Note the shape of this check. The naive version -- "reject only if
            # the bytes look like some OTHER known format" -- lets anything we
            # do not recognise straight through, including a Windows executable
            # labelled application/pdf. So for every format we CAN verify, the
            # signature must match; unrecognised bytes are a failure, not a pass.
            raise UploadRejected(
                f"That file is labelled {declared}, but its contents are not. "
                f"Please re-save it and try again."
            )

        # The name is ours alone. A filename from a browser is attacker input:
        # `../../etc/passwd`, a 4,000-character name, a NUL byte, a leading
        # dash that the next shell command reads as a flag. None of that can
        # reach the filesystem if we never use it.
        name = uuid.uuid4().hex
        relative = Path(name[:2]) / name[2:4] / f"{name}{ALLOWED_TYPES[declared]}"
        destination = self._root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)

        return StoredFile(
            path=str(relative), size_bytes=len(content), content_type=declared
        )

    def open(self, path: str) -> bytes:
        return self._resolve(path).read_bytes()

    def delete(self, path: str) -> None:
        self._resolve(path).unlink(missing_ok=True)

    def _resolve(self, path: str) -> Path:
        """Turn a stored path back into a real one, refusing to leave the root.

        Every stored path was generated by `save`, so this should never fire.
        It is here because "should never" and "cannot" are different, and the
        gap between them is where directory traversal lives.
        """
        candidate = (self._root / path).resolve()
        root = self._root.resolve()
        if not candidate.is_relative_to(root):
            raise UploadRejected("That file is not where it should be.")
        return candidate


def _sniff(content: bytes) -> str | None:
    """What the first bytes say the file really is, or None if we cannot tell."""
    for signature, content_type in _SIGNATURES:
        if content.startswith(signature):
            return content_type
    return None
