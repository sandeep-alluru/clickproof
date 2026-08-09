"""INVISIBLE-INK - adversarial goals behind legitimate CUA tasks.

Public case (Track B 20260807T161233Z):
  Invisible Ink Threats (arXiv 2608.02018) - adversarial goals behind
  legitimate computer-use tasks. Also maps to CUA/Qwen-CUA/Screenshots-or-Tools.

Pre-fix hole: agent is given "close the dialog" but UI injection or drift
proposes delete/export/auth; no gate compares proposed action to task scope.
"""

from __future__ import annotations

import pytest

from clickproof.closed_loop import (
    ClosedLoopError,
    assert_task_aligned,
    gate_task_alignment,
    infer_allowlist_from_task,
    is_high_risk_cua_action,
)


def test_is_high_risk_cua_action() -> None:
    assert is_high_risk_cua_action("delete") is True
    assert is_high_risk_cua_action("export_data") is True
    assert is_high_risk_cua_action("click") is False
    assert is_high_risk_cua_action("") is True


def test_empty_task_fails_loud() -> None:
    out = gate_task_alignment("", "click")
    assert out.ok is False
    assert out.verdict == "FAIL_LOUD"
    assert out.human_required is True
    assert "INVISIBLE-INK" in out.reason


def test_empty_action_fails_loud() -> None:
    out = gate_task_alignment("close the settings dialog", "")
    assert out.verdict == "FAIL_LOUD"


def test_benign_close_dialog_allows_click() -> None:
    task = "Please close the settings dialog"
    out = gate_task_alignment(task, "click")
    assert out.ok is True
    assert out.verdict == "PASS"
    assert out.risk == "safe"
    out2 = gate_task_alignment(task, "close")
    assert out2.ok is True


def test_invisible_ink_delete_behind_close_task_fails() -> None:
    """Classic Invisible Ink: legitimate close task, adversarial delete."""
    task = "Close the cookie banner on the homepage"
    out = gate_task_alignment(task, "delete")
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert out.exit_code == 1
    assert out.human_required is True
    assert out.action == "delete"
    assert out.risk == "high_risk"
    assert "2608.02018" in out.reason or "INVISIBLE-INK" in out.reason
    payload = out.to_dict()
    assert payload["human_required"] is True
    assert payload["action"] == "delete"


def test_export_not_in_task_fails() -> None:
    out = gate_task_alignment(
        "Open the profile page and screenshot the header",
        "export_data",
    )
    assert out.ok is False
    assert out.risk == "high_risk"


def test_explicit_allowlist_authorises_delete() -> None:
    out = gate_task_alignment(
        "Remove the draft post",
        "delete",
        allowed_actions=["delete", "click", "confirm"],
        infer_from_task=False,
    )
    assert out.ok is True
    assert out.verdict == "PASS"


def test_infer_allowlist_includes_delete_when_task_says_delete() -> None:
    allow = infer_allowlist_from_task("delete the temporary draft file")
    assert "delete" in allow
    out = gate_task_alignment("delete the temporary draft file", "delete")
    assert out.ok is True


def test_target_outside_allowlist_fails() -> None:
    out = gate_task_alignment(
        "Click the Save button",
        "click",
        allowed_actions=["click"],
        target="#delete-account",
        allowed_targets=["#save", "#cancel"],
        infer_from_task=False,
    )
    assert out.ok is False
    assert "target" in out.reason.lower() or "INVISIBLE-INK" in out.reason


def test_target_in_allowlist_passes() -> None:
    out = gate_task_alignment(
        "Click Save",
        "click",
        allowed_actions=["click"],
        target="#save",
        allowed_targets=["#save", "#cancel"],
        infer_from_task=False,
    )
    assert out.ok is True


def test_assert_task_aligned_raises() -> None:
    with pytest.raises(ClosedLoopError):
        assert_task_aligned("dismiss modal", "wipe")


def test_assert_task_aligned_passes() -> None:
    out = assert_task_aligned("scroll the feed", "scroll")
    assert out.ok is True
