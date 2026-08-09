"""CVE — Contextual Variable Overestimation (arXiv 2608.04504 GeoReward)."""

from __future__ import annotations

import pytest

from clickproof.closed_loop import ClosedLoopError
from clickproof.context_vars import (
    ContextDecision,
    analyze_cve,
    assert_context_variables_ok,
    context_fingerprint,
    gate_context_variables,
    is_sparse_context_key,
)


def test_is_sparse_context_key() -> None:
    assert is_sparse_context_key("market") is True
    assert is_sparse_context_key("country_code") is True
    assert is_sparse_context_key("product") is False


def test_empty_fails_loud() -> None:
    out = gate_context_variables(None)
    assert out.ok is False
    assert out.verdict == "FAIL_LOUD"


def test_missing_required_sparse_fails_loud() -> None:
    d = ContextDecision(
        "d1",
        choice="creative_A",
        sparse_context={},
        dominant_cues={"product": "shoes", "color": "red"},
        attended_keys=("product",),
    )
    out = gate_context_variables(d, required_sparse_keys=["market"])
    assert out.ok is False
    assert out.verdict == "FAIL_LOUD"
    assert "missing" in out.reason.lower() or "empty" in out.reason.lower()


def test_dominant_only_fails() -> None:
    d = ContextDecision(
        "d2",
        choice="creative_A",
        sparse_context={"market": "JP"},
        dominant_cues={"product": "shoes", "image": "hero.png"},
        attended_keys=("product", "image"),  # ignored market
    )
    out = gate_context_variables(d, require_attended=True, refuse_dominant_only=True)
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert "CVE" in out.reason or "GeoReward" in out.reason


def test_attended_sparse_passes() -> None:
    d = ContextDecision(
        "d3",
        choice="creative_JP",
        sparse_context={"market": "JP", "locale": "ja-JP"},
        dominant_cues={"product": "shoes"},
        attended_keys=("market", "locale", "product"),
    )
    out = gate_context_variables(d)
    assert out.ok is True
    assert out.verdict == "PASS"


def test_cross_context_collapse_fails() -> None:
    batch = [
        {
            "decision_id": "b1",
            "choice": "same_creative",
            "sparse_context": {"market": "US"},
            "dominant_cues": {"product": "x"},
            "attended_keys": ["market"],
        },
        {
            "decision_id": "b2",
            "choice": "same_creative",
            "sparse_context": {"market": "JP"},
            "dominant_cues": {"product": "x"},
            "attended_keys": ["market"],
        },
    ]
    out = gate_context_variables(batch[0], batch=batch, refuse_cross_context_collapse=True)
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert "collapse" in out.reason.lower()


def test_distinct_choices_no_collapse() -> None:
    batch = [
        ContextDecision(
            "c1",
            "creative_US",
            sparse_context={"market": "US"},
            dominant_cues={"product": "x"},
            attended_keys=("market",),
        ),
        ContextDecision(
            "c2",
            "creative_JP",
            sparse_context={"market": "JP"},
            dominant_cues={"product": "x"},
            attended_keys=("market",),
        ),
    ]
    out = gate_context_variables(batch[0], batch=batch)
    assert out.ok is True


def test_fingerprint() -> None:
    assert context_fingerprint({"market": "US", "locale": "en"}) == "locale=en|market=US"


def test_assert_raises() -> None:
    with pytest.raises(ClosedLoopError):
        assert_context_variables_ok(
            ContextDecision("x", "a", sparse_context={}, dominant_cues={"p": 1}),
        )


def test_arxiv_georeward_fixture() -> None:
    """End-to-end: VLM collapses market preference → refuse; market-aware → pass."""
    # Pre-fix: same creative for US and DE despite different markets
    collapse = gate_context_variables(
        {
            "id": "geo1",
            "choice": "global_hero",
            "context": {"market": "US"},
            "dominant": {"product": "sneakers", "color": "white"},
            "attended": ["product", "color"],
            "by_context": {
                "market=US": "global_hero",
                "market=DE": "global_hero",
            },
        },
        required_sparse_keys=["market"],
    )
    # attended ignores market → dominant_only or ignore fail; also collapse
    assert collapse.ok is False

    ok = gate_context_variables(
        {
            "decision_id": "geo2",
            "choice": "hero_de",
            "sparse_context": {"market": "DE", "locale": "de-DE"},
            "dominant_cues": {"product": "sneakers"},
            "attended_keys": ["market", "locale", "product"],
            "choice_by_context": {
                "market=US|locale=en-US": "hero_us",
                "market=DE|locale=de-DE": "hero_de",
            },
        },
        required_sparse_keys=["market"],
    )
    assert ok.ok is True
    assert ok.verdict == "PASS"
    rep = analyze_cve(
        ContextDecision(
            "geo2",
            "hero_de",
            sparse_context={"market": "DE"},
            attended_keys=("market",),
        )
    )
    assert "market" in rep.sparse_keys_present
