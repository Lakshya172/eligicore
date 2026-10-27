"""Searching captured logs for privacy markers without tripping over unrelated numbers.

The privacy tests plant marker values in a profile and assert that none reaches a log. Most
markers are nonsense strings, and plain containment is exactly right for them. A few have to
be numbers, because the field they stand in for is one: a CGPA (``8.63``), a graduation year
(``2027``), a score (``61.37``).

A numeric marker cannot be searched as a bare substring of ``str(record.args)``. The args
tuples carry *unrounded* float timings, which the rendered lines format away
(``duration_ms=%.1f``), and a float repr has up to seventeen significant digits, so any short
digit run is eventually a substring of one. That flake has been seen twice:

* ``6.83`` inside ``16.830941107869148``, fixed for ``test_production_configuration.py`` in
  PR #53 (``fix/privacy-marker-flake``);
* ``2027`` inside ``0.02027799999382296``, CI run 40530305768 on ``main`` at ``e85a70e``, in
  ``test_eligibility_ai_stage.py::test_ai_inputs_prompts_and_responses_are_not_logged``.

Making the marker longer does not help. This module applies the rule PR #53 established: a
numeric marker counts only where it is the whole number. The haystack is read as the numbers
it is written with (digits, an optional fraction, an optional exponent, each taken whole), and
the marker is a leak where one of them has the marker's value. So ``cgpa=8.63``, ``(8.63,)``,
``8.630``, ``... is 2027.``, ``2027-06`` and ``2027.0`` are leaks, while ``18.63``, ``8.631``,
``0.0202779…``, a ``2027.45`` ms duration and ``8.63e-05`` are other numbers, and are not. A
character check either side of the marker cannot tell those apart; comparing values can.
"""

from __future__ import annotations

import re
from decimal import Decimal

#: A marker made only of digits and dots is matched as a whole number, not as a substring.
PURELY_NUMERIC = re.compile(r"[0-9.]+\Z")
#: One whole number as a log writes it, taken at its longest: ``8``, ``8.63``, ``8.63e-05``.
NUMBER = re.compile(r"\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")


def contains_marker(haystack: str, marker: str) -> bool:
    """Whether `marker` appears in `haystack` as a marker, not as part of a longer number."""
    if PURELY_NUMERIC.match(marker):
        value = Decimal(marker)
        return any(Decimal(number) == value for number in NUMBER.findall(haystack))
    return marker in haystack
