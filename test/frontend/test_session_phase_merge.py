"""
applyExploreResumeToSession 阶段合并逻辑测试。

TDD: 纯函数语义验证 — 当本地状态领先后端时，合并不应回退。

The logic below is a faithful Python port of the TypeScript function
in src/frontend/lib/explore/session.ts so that we can test the merge
semantics without needing a JS test runner.
"""

# ── Phase model (mirrors TypeScript PHASES array) ───────────────────

PHASES = ["values", "strengths", "interests", "purpose", "rumination"]


def phase_index(key: str) -> int:
    idx = PHASES.index(key) if key in PHASES else -1
    return idx


# ── Python port of applyExploreResumeToSession ──────────────────────

def apply_explore_resume(session: dict, resume: dict | None) -> dict:
    """
    Python equivalent of the TypeScript applyExploreResumeToSession.
    This port mirrors the ORIGINAL (buggy) behavior so that the tests
    demonstrate the bug. We will update it to match the fixed TS code
    once tests pass.
    """
    rp = (resume or {}).get("resume_phase")
    if not rp:
        return session
    if rp not in PHASES:
        return session

    raw = (resume or {}).get("unlocked_phases")
    backend_unlocked = [k for k in (raw or []) if k in PHASES]
    if not backend_unlocked:
        idx = PHASES.index(rp)
        backend_unlocked = list(PHASES[: idx + 1])

    return {
        **session,
        "currentPhase": rp,
        "unlockedPhases": backend_unlocked,
    }


def apply_explore_resume_fixed(session: dict, resume: dict | None) -> dict:
    """
    Python equivalent of the FIXED TypeScript applyExploreResumeToSession.
    Takes the union of unlockedPhases and uses whichever currentPhase is further ahead.
    """
    rp = (resume or {}).get("resume_phase")
    if not rp:
        return session
    if rp not in PHASES:
        return session

    raw = (resume or {}).get("unlocked_phases")
    backend_unlocked = [k for k in (raw or []) if k in PHASES]
    if not backend_unlocked:
        idx = PHASES.index(rp)
        backend_unlocked = list(PHASES[: idx + 1])

    # Union of local + backend, preserving phase order
    merged_unlocked = [p for p in PHASES if p in session.get("unlockedPhases", []) or p in backend_unlocked]

    # currentPhase: whichever is further ahead
    local_idx = phase_index(session.get("currentPhase", "values"))
    backend_idx = phase_index(rp)
    merged_current = rp if backend_idx > local_idx else session.get("currentPhase", "values")

    # Short-circuit if nothing changed (preserve object identity in spirit)
    local_unlocked = session.get("unlockedPhases", [])
    if (
        merged_current == session.get("currentPhase")
        and len(merged_unlocked) == len(local_unlocked)
        and all(a == b for a, b in zip(merged_unlocked, local_unlocked))
    ):
        return session

    return {
        **session,
        "currentPhase": merged_current,
        "unlockedPhases": merged_unlocked,
    }


# ── Helpers ─────────────────────────────────────────────────────────

def make_session(current_phase: str, unlocked: list[str]) -> dict:
    return {
        "activationCode": "TEST",
        "currentPhase": current_phase,
        "unlockedPhases": unlocked,
        "surveyCompleted": True,
    }


def make_resume(resume_phase: str, unlocked_phases: list[str] | None = None) -> dict:
    return {
        "resume_phase": resume_phase,
        "unlocked_phases": unlocked_phases,
    }


# ═══════════════════════════════════════════════════════════════════
# TEST 1 (tracer bullet): local state ahead of backend — MUST NOT regress
# ═══════════════════════════════════════════════════════════════════

class TestLocalAheadOfBackend:
    """Bug scenario: user clicked '完成并继续', localStorage advanced,
    but backend still returns the old phase because lock_step hasn't fired yet."""

    def test_current_phase_not_regressed_when_local_ahead(self):
        """Local is at 'strengths', backend says 'values' → stay at 'strengths'"""
        session = make_session("strengths", ["values", "strengths"])
        resume = make_resume("values", ["values"])

        result = apply_explore_resume_fixed(session, resume)

        assert result["currentPhase"] == "strengths", (
            f"Expected currentPhase='strengths' but got '{result['currentPhase']}'"
        )

    def test_unlocked_phases_not_shrunk(self):
        """Local has [values, strengths], backend has [values] → union = [values, strengths]"""
        session = make_session("strengths", ["values", "strengths"])
        resume = make_resume("values", ["values"])

        result = apply_explore_resume_fixed(session, resume)

        assert result["unlockedPhases"] == ["values", "strengths"], (
            f"Expected ['values', 'strengths'] but got {result['unlockedPhases']}"
        )

    def test_values_to_strengths_transition(self):
        """Exact race condition: completed values, navigating to strengths,
        backend still says resume_phase=values"""
        session = make_session("strengths", ["values", "strengths"])
        resume = make_resume("values", ["values"])

        result = apply_explore_resume_fixed(session, resume)

        assert result["currentPhase"] == "strengths"
        assert "strengths" in result["unlockedPhases"]

    def test_strengths_to_interests_transition(self):
        """Same pattern one step further"""
        session = make_session("interests", ["values", "strengths", "interests"])
        resume = make_resume("strengths", ["values", "strengths"])

        result = apply_explore_resume_fixed(session, resume)

        assert result["currentPhase"] == "interests"
        assert result["unlockedPhases"] == ["values", "strengths", "interests"]

    def test_original_behavior_is_buggy(self):
        """Demonstrate that the ORIGINAL function regresses state (this test
        shows the bug exists)."""
        session = make_session("strengths", ["values", "strengths"])
        resume = make_resume("values", ["values"])

        result = apply_explore_resume(session, resume)

        # Original function incorrectly overwrites
        assert result["currentPhase"] == "values", "Original code has the bug: it regresses to 'values'"
        assert result["unlockedPhases"] == ["values"], "Original code shrinks unlockedPhases"


# ═══════════════════════════════════════════════════════════════════
# TEST 2: Backend ahead — cross-device sync should still advance
# ═══════════════════════════════════════════════════════════════════

class TestBackendAheadOfLocal:
    """Cross-device scenario: user completed a phase on another device,
    backend has progressed, local is stale."""

    def test_backend_ahead_advances_current_phase(self):
        """Local is at 'values', backend says 'strengths' → advance to 'strengths'"""
        session = make_session("values", ["values"])
        resume = make_resume("strengths", ["values", "strengths"])

        result = apply_explore_resume_fixed(session, resume)

        assert result["currentPhase"] == "strengths"

    def test_backend_ahead_adds_to_unlocked(self):
        """Local [values], backend [values, strengths] → union [values, strengths]"""
        session = make_session("values", ["values"])
        resume = make_resume("strengths", ["values", "strengths"])

        result = apply_explore_resume_fixed(session, resume)

        assert result["unlockedPhases"] == ["values", "strengths"]

    def test_backend_two_steps_ahead(self):
        """Local [values], backend says rumination → should advance to rumination"""
        session = make_session("values", ["values"])
        resume = make_resume("rumination", ["values", "strengths", "interests", "purpose", "rumination"])

        result = apply_explore_resume_fixed(session, resume)

        assert result["currentPhase"] == "rumination"
        assert result["unlockedPhases"] == ["values", "strengths", "interests", "purpose", "rumination"]


# ═══════════════════════════════════════════════════════════════════
# TEST 3: Local == Backend — no change
# ═══════════════════════════════════════════════════════════════════

class TestEqualStates:
    """When local and backend are in sync, no changes should be made."""

    def test_same_phase_same_unlocked(self):
        session = make_session("strengths", ["values", "strengths"])
        resume = make_resume("strengths", ["values", "strengths"])

        result = apply_explore_resume_fixed(session, resume)

        # Should return same session (no-op)
        assert result["currentPhase"] == "strengths"
        assert result["unlockedPhases"] == ["values", "strengths"]

    def test_preserves_other_session_fields(self):
        """Other fields like activationCode, surveyCompleted must not be lost"""
        session = make_session("values", ["values"])
        session["reportReady"] = True
        session["activationSessionId"] = "sess_123"

        result = apply_explore_resume_fixed(session, make_resume("values", ["values"]))

        assert result["activationCode"] == "TEST"
        assert result["surveyCompleted"] is True
        assert result["reportReady"] is True
        assert result["activationSessionId"] == "sess_123"


# ═══════════════════════════════════════════════════════════════════
# TEST 4: Null / empty resume — no change
# ═══════════════════════════════════════════════════════════════════

class TestNullResume:
    """Edge cases: missing or empty resume data."""

    def test_none_resume(self):
        session = make_session("strengths", ["values", "strengths"])
        result = apply_explore_resume_fixed(session, None)
        assert result["currentPhase"] == "strengths"

    def test_empty_dict_resume(self):
        session = make_session("strengths", ["values", "strengths"])
        result = apply_explore_resume_fixed(session, {})
        assert result["currentPhase"] == "strengths"

    def test_missing_resume_phase(self):
        session = make_session("strengths", ["values", "strengths"])
        result = apply_explore_resume_fixed(session, {"unlocked_phases": ["values"]})
        assert result["currentPhase"] == "strengths"


# ═══════════════════════════════════════════════════════════════════
# TEST 5: Invalid resume_phase — no change
# ═══════════════════════════════════════════════════════════════════

class TestInvalidResumePhase:
    """Backend returns an unknown phase key — should be ignored."""

    def test_unknown_phase_key(self):
        session = make_session("strengths", ["values", "strengths"])
        result = apply_explore_resume_fixed(session, {"resume_phase": "nonexistent"})
        assert result["currentPhase"] == "strengths"

    def test_empty_string_phase(self):
        session = make_session("strengths", ["values", "strengths"])
        result = apply_explore_resume_fixed(session, {"resume_phase": ""})
        assert result["currentPhase"] == "strengths"


# ═══════════════════════════════════════════════════════════════════
# TEST 6: Rumination edge case
# ═══════════════════════════════════════════════════════════════════

class TestRuminationEdge:
    """Rumination is the last phase — no further advancement possible."""

    def test_rumination_local_ahead(self):
        """Local at rumination, backend says purpose → stay at rumination"""
        session = make_session("rumination", ["values", "strengths", "interests", "purpose", "rumination"])
        resume = make_resume("purpose", ["values", "strengths", "interests", "purpose"])

        result = apply_explore_resume_fixed(session, resume)

        assert result["currentPhase"] == "rumination"
        assert result["unlockedPhases"] == ["values", "strengths", "interests", "purpose", "rumination"]

    def test_rumination_backend_ahead(self):
        """Local at purpose, backend says rumination → advance"""
        session = make_session("purpose", ["values", "strengths", "interests", "purpose"])
        resume = make_resume("rumination", ["values", "strengths", "interests", "purpose", "rumination"])

        result = apply_explore_resume_fixed(session, resume)

        assert result["currentPhase"] == "rumination"
        assert result["unlockedPhases"] == ["values", "strengths", "interests", "purpose", "rumination"]


# ═══════════════════════════════════════════════════════════════════
# TEST 7: Fresh session (first phase default)
# ═══════════════════════════════════════════════════════════════════

class TestFreshSession:
    """User just started — only values unlocked."""

    def test_fresh_session_backend_says_values(self):
        session = make_session("values", ["values"])
        resume = make_resume("values", ["values"])

        result = apply_explore_resume_fixed(session, resume)

        assert result["currentPhase"] == "values"
        assert result["unlockedPhases"] == ["values"]

    def test_fresh_session_no_backend_resume(self):
        session = make_session("values", ["values"])
        result = apply_explore_resume_fixed(session, None)
        assert result["currentPhase"] == "values"


# ═══════════════════════════════════════════════════════════════════
# TEST 8: Backend unlocked_phases missing — derive from resume_phase
# ═══════════════════════════════════════════════════════════════════

class TestBackendUnlockedMissing:
    """Backend returns resume_phase but no unlocked_phases — should derive."""

    def test_derive_unlocked_from_resume_phase(self):
        """resume_phase=strengths, no unlocked_phases → derive [values, strengths]"""
        session = make_session("strengths", ["values", "strengths"])
        resume = make_resume("strengths", None)

        result = apply_explore_resume_fixed(session, resume)

        # Union of local [values, strengths] and derived [values, strengths] = same
        assert result["unlockedPhases"] == ["values", "strengths"]
        assert result["currentPhase"] == "strengths"

    def test_derive_with_local_ahead(self):
        """resume_phase=values (derived → [values]), local has [values, strengths]
        → union [values, strengths], currentPhase stays at strengths"""
        session = make_session("strengths", ["values", "strengths"])
        resume = make_resume("values", None)

        result = apply_explore_resume_fixed(session, resume)

        assert result["currentPhase"] == "strengths"
        assert result["unlockedPhases"] == ["values", "strengths"]
