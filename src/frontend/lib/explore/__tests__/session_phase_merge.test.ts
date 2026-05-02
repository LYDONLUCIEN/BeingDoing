/**
 * Direct test of applyExploreResumeToSession from session.ts.
 * Run: cd src/frontend && npx tsx lib/explore/__tests__/session_phase_merge.test.ts
 *
 * This exercises the REAL TypeScript function — not a Python port.
 */

import {
  type ExploreSession,
  type ExploreResumePayload,
  PHASES,
  applyExploreResumeToSession,
} from '../session';

// ── Helpers ─────────────────────────────────────────────────────────

function makeSession(currentPhase: string, unlocked: string[]): ExploreSession {
  return {
    activationCode: 'TEST',
    currentPhase: currentPhase as ExploreSession['currentPhase'],
    unlockedPhases: unlocked as ExploreSession['unlockedPhases'],
    surveyCompleted: true,
  };
}

function makeResume(resumePhase: string, unlockedPhases: string[] | null = null): ExploreResumePayload {
  return { resume_phase: resumePhase, unlocked_phases: unlockedPhases };
}

let passed = 0;
let failed = 0;

function assert(condition: boolean, message: string) {
  if (!condition) {
    failed++;
    console.error(`  FAIL: ${message}`);
    return false;
  }
  passed++;
  return true;
}

function describe(name: string, fn: () => void) {
  console.log(`\n${name}`);
  fn();
}

// ── Tests ───────────────────────────────────────────────────────────

describe('Local ahead of backend (bug scenario)', () => {
  const session = makeSession('strengths', ['values', 'strengths']);
  const resume = makeResume('values', ['values']);
  const result = applyExploreResumeToSession(session, resume);

  assert(result.currentPhase === 'strengths',
    `currentPhase should stay 'strengths', got '${result.currentPhase}'`);
  assert(result.unlockedPhases.length === 2,
    `unlockedPhases should have 2 items, got ${result.unlockedPhases.length}`);
  assert(result.unlockedPhases.includes('strengths'),
    'unlockedPhases should include strengths');
});

describe('Backend ahead (cross-device sync)', () => {
  const session = makeSession('values', ['values']);
  const resume = makeResume('strengths', ['values', 'strengths']);
  const result = applyExploreResumeToSession(session, resume);

  assert(result.currentPhase === 'strengths',
    `currentPhase should advance to 'strengths', got '${result.currentPhase}'`);
  assert(result.unlockedPhases.includes('strengths'),
    'unlockedPhases should include strengths');
});

describe('Equal states (no change)', () => {
  const session = makeSession('strengths', ['values', 'strengths']);
  const resume = makeResume('strengths', ['values', 'strengths']);
  const result = applyExploreResumeToSession(session, resume);

  assert(result.currentPhase === 'strengths',
    'currentPhase should remain strengths');
  assert(result.unlockedPhases.length === 2,
    'unlockedPhases should remain 2 items');
});

describe('Null resume', () => {
  const session = makeSession('strengths', ['values', 'strengths']);
  const r1 = applyExploreResumeToSession(session, null);
  const r2 = applyExploreResumeToSession(session, {});
  const r3 = applyExploreResumeToSession(session, { unlocked_phases: ['values'] });

  assert(r1.currentPhase === 'strengths', 'null resume: should stay at strengths');
  assert(r2.currentPhase === 'strengths', 'empty resume: should stay at strengths');
  assert(r3.currentPhase === 'strengths', 'missing resume_phase: should stay at strengths');
});

describe('Invalid resume_phase', () => {
  const session = makeSession('strengths', ['values', 'strengths']);
  const r1 = applyExploreResumeToSession(session, { resume_phase: 'nonexistent' });
  const r2 = applyExploreResumeToSession(session, { resume_phase: '' });

  assert(r1.currentPhase === 'strengths', 'unknown phase: should stay at strengths');
  assert(r2.currentPhase === 'strengths', 'empty phase: should stay at strengths');
});

describe('Rumination edge', () => {
  const ahead = makeSession('rumination',
    ['values', 'strengths', 'interests', 'purpose', 'rumination']);
  const behind = makeResume('purpose',
    ['values', 'strengths', 'interests', 'purpose']);
  const result = applyExploreResumeToSession(ahead, behind);

  assert(result.currentPhase === 'rumination',
    `should stay at rumination, got '${result.currentPhase}'`);
  assert(result.unlockedPhases.length === 5,
    `should have all 5 phases, got ${result.unlockedPhases.length}`);
});

describe('Backend unlocked_phases missing (derive)', () => {
  const session = makeSession('strengths', ['values', 'strengths']);
  const resume = makeResume('values', null);
  const result = applyExploreResumeToSession(session, resume);

  assert(result.currentPhase === 'strengths',
    `local ahead, derived backend: should stay 'strengths', got '${result.currentPhase}'`);
  assert(result.unlockedPhases.includes('strengths'),
    'should keep strengths in unlocked');
});

describe('Preserves other session fields', () => {
  const session: ExploreSession = {
    ...makeSession('strengths', ['values', 'strengths']),
    reportReady: true,
    activationSessionId: 'sess_123',
  };
  const result = applyExploreResumeToSession(session, makeResume('strengths', ['values', 'strengths']));

  assert(result.activationCode === 'TEST', 'activationCode preserved');
  assert(result.surveyCompleted === true, 'surveyCompleted preserved');
  assert(result.reportReady === true, 'reportReady preserved');
  assert(result.activationSessionId === 'sess_123', 'activationSessionId preserved');
});

// ── Summary ─────────────────────────────────────────────────────────

console.log(`\n${'='.repeat(50)}`);
console.log(`Results: ${passed} passed, ${failed} failed`);
if (failed > 0) {
  process.exit(1);
}
