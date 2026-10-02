"""Which uploaded documents still have their bytes.

WHY THIS EXISTS

`documents` records where a file is. The bytes live in storage. Nothing
ever checked that the two still agree, and for a long time they did not:
`upload_dir` defaulted to a path inside the container, and a container on
Render is rebuilt from its image on every deploy. Every receipt, boarding
pass and booking confirmation a customer uploaded was destroyed by the
next push.

Nothing noticed, because nothing ever read a file back. The rows were
still there, the claim still said "3 files", and the loss only surfaced
when the operator console tried to show a thumbnail.

So this walks every row and asks storage whether the file is really
there. It changes nothing: a row whose bytes are gone is still the record
that the customer sent us something, and deleting it would destroy the
only evidence that they did. What an operator needs is the list -- who to
ask, and for what.

    ./prod files              every claim with a missing file
    ./prod files --summary    just the counts
"""

from __future__ import annotations

import argparse
from collections import defaultdict

from sqlalchemy import select

from app.config import get_settings
from app.db.models import Claim, Document
from app.db.session import create_db_engine, create_session_factory, session_scope
from app.storage.files import LocalFileStorage


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--summary", action="store_true", help="Counts only, no per-claim list."
    )
    args = parser.parse_args()

    settings = get_settings()
    storage = LocalFileStorage(settings.upload_dir)
    engine = create_db_engine(settings.database_url)

    # THIS ONLY MEANS ANYTHING WHERE THE FILES ARE.
    #
    # Run from a laptop against the production database, it checks the
    # production rows against the LAPTOP's disk and reports that
    # everything is missing -- which is true locally and says nothing
    # about the server. The answer would be alarming and wrong.
    print(f"\n  storage: {settings.upload_dir.resolve()}")
    if not settings.upload_dir.exists() or not any(
        settings.upload_dir.rglob("*")
    ):
        print(
            "  WARNING: that directory is empty or absent. If you are not "
            "running\n           this on the server, the result below is "
            "about this machine\n           and tells you nothing about "
            "production."
        )

    present = 0
    missing: dict[str, list[Document]] = defaultdict(list)

    with session_scope(create_session_factory(engine)) as session:
        documents = session.scalars(
            select(Document).order_by(Document.created_at)
        ).all()

        for document in documents:
            try:
                storage.open(document.stored_path)
            except (FileNotFoundError, OSError):
                # ONE COLUMN, not the Claim object.
                #
                # Loading the ORM entity pulls in its passengers, whose
                # identity numbers are encrypted -- so a task that only
                # wants an email address would need ENCRYPTION_KEYS and
                # would decrypt every national ID in the database to
                # print a list of filenames. It crashed on exactly that.
                #
                # Keyed by the person rather than the claim id: the output
                # is a list of people to write to, and nobody can write to
                # a UUID.
                who = session.scalar(
                    select(Claim.contact_email).where(
                        Claim.id == document.claim_id
                    )
                )
                missing[who or "unknown"].append(document)
            else:
                present += 1

        total = len(documents)
        print(f"\n  {total:>5}  uploaded documents on record")
        print(f"  {present:>5}  still have their bytes")
        print(f"  {sum(len(v) for v in missing.values()):>5}  do NOT\n")

        if not missing:
            print("  Nothing is missing.\n")
            return 0

        if not args.summary:
            print("  Ask these customers to upload again:\n")
            for who, docs in sorted(missing.items()):
                print(f"    {who}")
                for d in docs:
                    print(
                        f"        {d.created_at:%Y-%m-%d}  {d.kind:<16} "
                        f"{d.original_filename}"
                    )
            print()

    # A non-zero exit so this is usable as a check in a pipeline: "some
    # evidence is missing" is a failure state, even though the command
    # itself worked perfectly.
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
