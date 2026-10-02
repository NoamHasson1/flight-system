"""Every question a rule can ask must be a question the interface can put.

WHY THIS TEST EXISTS

`OpenQuestion` is a closed enum precisely so a rule cannot invent a question
the front end has no way to ask. That guarantee was never actually checked,
and the failure it guards against is silent by construction:

    strings.questions[key as keyof typeof strings.questions]
      ... .filter(Boolean)

An unrecognised key yields `undefined` and `filter(Boolean)` drops it. No
error, no warning, no blank space -- the question simply does not appear.
The customer sees a page saying they are owed ILS1,530 "pending one detail"
and is never told which detail. The claim then cannot be completed, and
nothing anywhere reports a problem.

That is exactly what would have happened when ACTUAL_DEPARTURE was added to
the rules: the backend was correct, the tests were green, and 82 flights
would have rendered a question nobody could answer.

Reading the other language's source file from a test is unusual, and it is
the right trade here. The alternative is a list in each language that drifts
apart, which is the bug rather than a test for it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.domain.rules.base import OpenQuestion

STRINGS = (
    Path(__file__).resolve().parents[2].parent / "frontend" / "src" / "lib" / "strings.ts"
)


def _question_keys_in_the_interface() -> set[str]:
    """The keys defined under `questions: { ... }` in the Hebrew strings."""
    source = STRINGS.read_text(encoding="utf-8")
    block = re.search(r"\n  questions: \{(.+?)\n  \},\n", source, re.S)
    assert block, "could not find the `questions` block in strings.ts"
    return set(re.findall(r"^    (\w+): \{", block.group(1), re.M))


@pytest.mark.skipif(not STRINGS.exists(), reason="frontend not checked out")
def test_every_rule_question_has_wording_in_the_interface() -> None:
    """A rule may not ask something the customer cannot be shown.

    If this fails, a verdict is reaching somebody with an invisible
    condition attached. Add the key to `questions` in strings.ts.
    """
    missing = {q.value for q in OpenQuestion} - _question_keys_in_the_interface()

    assert not missing, (
        f"these questions can be asked by a rule but have no wording: "
        f"{sorted(missing)} -- they would vanish from the page silently"
    )


@pytest.mark.skipif(not STRINGS.exists(), reason="frontend not checked out")
def test_the_interface_does_not_ask_anything_the_rules_cannot_produce() -> None:
    """The other direction, which is untidiness rather than a live bug.

    Wording for a question no rule emits is dead text that will be
    translated, reviewed and maintained forever by people who assume it is
    reachable. It usually means a question was renamed on one side only --
    and the renamed half shows up in the test above as a real failure.
    """
    orphans = _question_keys_in_the_interface() - {q.value for q in OpenQuestion}

    assert not orphans, (
        f"the interface has wording for questions no rule asks: {sorted(orphans)}"
    )
