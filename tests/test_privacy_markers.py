"""`contains_marker` held from both sides: deaf to unrelated numbers, never blind to a leak.

Every log-privacy assertion that uses it is only as good as it is. Nothing here depends on the
clock: the colliding floats are written out.
"""

from __future__ import annotations

import pytest

from tests.privacy_markers import contains_marker


@pytest.mark.parametrize(
    ("haystack", "marker"),
    [
        ("(0.20271,)", "2027"),
        ("'unknown', 0.02027799999382296)", "2027"),  # CI run 40530305768
        ("duration 12027.4", "2027"),
        ("(16.830941107869148,)", "6.83"),  # PR #53
        ("(18.63,)", "8.63"),
        ("(8.631,)", "8.63"),
    ],
)
def test_a_numeric_marker_inside_a_longer_number_is_not_a_leak(haystack: str, marker: str) -> None:
    assert marker in haystack, "the sample no longer contains the marker as a substring"
    assert not contains_marker(haystack, marker)


@pytest.mark.parametrize(
    "leak",
    ["2027", "grad_year=2027", "(2027,)", '{"grad_year": 2027}', "graduates in 2027.", "2027-06"],
)
def test_a_standalone_year_is_still_a_leak(leak: str) -> None:
    assert contains_marker(leak, "2027")


@pytest.mark.parametrize(
    "leak",
    ["8.63", "cgpa=8.63", "(8.63,)", "{'cgpa': 8.63}", "8.63 (SCALE_10)", "candidate has 8.63."],
)
def test_a_standalone_grade_is_still_a_leak(leak: str) -> None:
    assert contains_marker(leak, "8.63")


def test_text_markers_keep_plain_containment() -> None:
    assert contains_marker("prefixAiMarkerSkillsuffix", "AiMarkerSkill")
    assert contains_marker("tel:+199900051519", "+19990005151")
    assert contains_marker("due 2026-11-150", "2026-11-15")
    assert not contains_marker("nothing to see here", "AiMarkerSkill")
