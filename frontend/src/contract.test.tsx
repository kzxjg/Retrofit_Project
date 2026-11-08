// The page against the REAL questionnaire and the REAL server rules, not the hand-made TEST_SPEC.
//
// The other tests use testSpec.ts so they do not break whenever a question changes. That leaves a
// gap: the backend could rename a field, add a question type or tighten a limit and every frontend
// test would still pass while the real page broke. These tests close it by asking Django itself
// (through tools/spec_contract.py, no server needed) for the form and for its verdict on answers.
//
// They need the project's Python (.venv). Without it they are skipped, and say so.
/// <reference types="node" />
import { execFileSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { allFields, buildPayload, defaultWeights, fieldIssue, initialAnswers, validate } from './formLogic'
import { optionForZoneId } from './zones'
import type { Answers, ApiError, Field, Report, Spec } from './types'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const PYTHON = process.env.RETROFIT_PYTHON ?? resolve(ROOT, '.venv/bin/python')
const HAVE_PYTHON = existsSync(PYTHON)

function python(command: 'spec' | 'check', input?: unknown): unknown {
  const out = execFileSync(PYTHON, ['tools/spec_contract.py', command], {
    cwd: ROOT,
    input: input === undefined ? undefined : JSON.stringify(input),
    encoding: 'utf-8',
    maxBuffer: 50 * 1024 * 1024,
  })
  return JSON.parse(out)
}

type Verdict = { errors: ApiError[]; report: Report | null }
const serverCheck = (payloads: Record<string, unknown>[]) => python('check', payloads) as Verdict[]

// The question types the page knows how to draw (FieldControl.tsx and types.ts).
const PAGE_TYPES = ['text', 'select', 'number', 'currency', 'weights']

/** A complete set of answers, typed the way the page stores them (numbers as text). */
function sampleAnswers(spec: Spec, mode: 0 | 1 = 0): Answers {
  const answers: Answers = initialAnswers(spec)
  for (const f of allFields(spec)) {
    if (f.type === 'select') answers[f.id] = f.options![0]
    else if (f.type === 'number' || f.type === 'currency') answers[f.id] = String(f.min !== undefined && f.min >= 1 ? f.min : 1)
    else if (f.type === 'weights') answers[f.id] = defaultWeights(f)
    else if (f.format === 'postal_code') answers[f.id] = 'N9A 1A1'
  }
  const zone = allFields(spec).find((f) => f.id === 'zone')!
  answers.zone = optionForZoneId(zone.options!, zone.must_match_postal!.zones_by_letter.N[0])!
  const mode_ = allFields(spec).find((f) => f.id === 'preference_mode')!
  answers.preference_mode = mode_.options![mode]
  return answers
}

const serverFieldErrors = (verdict: Verdict, id: string) => verdict.errors.filter((e) => e.field === id)

afterEach(() => vi.unstubAllGlobals())

// Each test starts Python and Django, which takes several seconds (more under WSL on a Windows
// drive), so the default 5 s timeout is too short.
describe.skipIf(!HAVE_PYTHON)('the page and the real server agree', { timeout: 60_000 }, () => {
  const spec = HAVE_PYTHON ? (python('spec') as Spec) : ({ sections: [] } as Spec)
  const fields = allFields(spec)

  it('uses only question types the page can draw', () => {
    const unknown = fields.filter((f) => !PAGE_TYPES.includes(f.type)).map((f) => `${f.id}: ${f.type}`)
    expect(unknown).toEqual([])
  })

  it('has the two sections of questions the page puts in steps 1 and 2', () => {
    expect(spec.sections.map((s) => s.id)).toEqual(['home', 'priorities'])
  })

  it('draws every question of the home profile, and the map', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => spec })))
    render(<App />)
    for (const f of spec.sections[0].fields) expect(await screen.findByLabelText(f.label)).toBeTruthy()
  })

  it('has follow-up questions whose conditions can actually be met', () => {
    for (const f of fields.filter((x) => x.show_if)) {
      const parent = fields.find((x) => x.id === f.show_if!.field)
      expect(parent, `${f.id} depends on a missing question`).toBeDefined()
      expect(parent!.options ?? [], `${f.id} waits for an answer ${parent!.id} never offers`).toContain(f.show_if!.equals)
    }
  })

  it.each([['simple', 0], ['advanced', 1]])(
    'sends a complete %s form in a shape the server accepts and gets a report back',
    (_, mode) => {
      const answers = sampleAnswers(spec, mode as 0 | 1)
      expect(validate(spec, answers)).toEqual([])
      const [verdict] = serverCheck([buildPayload(spec, answers)])
      expect(verdict.errors).toEqual([])
      expect(verdict.report?.packages.length).toBeGreaterThan(0)
      for (const key of ['cost', 'incentive', 'net_cost', 'saving_pct', 'score', 'within_budget']) {
        expect(verdict.report!.packages[0]).toHaveProperty(key)
      }
    },
  )

  it('sends only questions the server knows', () => {
    for (const mode of [0, 1] as const) {
      const [verdict] = serverCheck([buildPayload(spec, sampleAnswers(spec, mode))])
      expect(verdict.errors.filter((e) => /unknown field/i.test(e.message))).toEqual([])
    }
  })

  it('agrees with the server on the limits of every typed number', () => {
    const base = sampleAnswers(spec)
    const cases: { field: Field; typed: string }[] = []
    for (const f of fields.filter((x) => x.type === 'number' || x.type === 'currency')) {
      const step = f.integer ? 1 : 0.5
      const values = new Set<number>([1])
      if (f.min !== undefined) [f.min, f.min - step].forEach((v) => values.add(v))
      if (f.max !== undefined) [f.max, f.max + step].forEach((v) => values.add(v))
      for (const v of values) cases.push({ field: f, typed: String(v) })
    }
    const verdicts = serverCheck(cases.map(({ field, typed }) => buildPayload(spec, { ...base, [field.id]: typed })))
    const disagreements = cases.flatMap(({ field, typed }, i) => {
      const answers = { ...base, [field.id]: typed }
      const pageOk = fieldIssue(field, typed, answers) === null
      const serverOk = serverFieldErrors(verdicts[i], field.id).length === 0
      return pageOk === serverOk ? [] : [`${field.id}=${typed}: page ${pageOk ? 'accepts' : 'refuses'}, server ${serverOk ? 'accepts' : 'refuses'}`]
    })
    expect(disagreements).toEqual([])
  })

  it('agrees with the server on which weights are acceptable', () => {
    const weights = fields.find((f) => f.type === 'weights')!
    const base = sampleAnswers(spec, 1)
    const ids = weights.criteria!.map((c) => c.id)
    const all = (n: number) => Object.fromEntries(ids.map((id) => [id, n]))
    const cases = [all(0), all(100), { ...all(0), [ids[0]]: 1 }, { ...all(10), [ids[0]]: 101 }, { ...all(10), [ids[0]]: -1 }]
    const verdicts = serverCheck(cases.map((w) => buildPayload(spec, { ...base, [weights.id]: w })))
    cases.forEach((w, i) => {
      const pageOk = fieldIssue(weights, w, base) === null
      expect(serverFieldErrors(verdicts[i], weights.id).length === 0, JSON.stringify(w)).toBe(pageOk)
    })
  })

  it('agrees with the server on which climate zones fit each postal code letter', () => {
    const zone = fields.find((f) => f.id === 'zone')!
    const base = sampleAnswers(spec)
    const letters = 'ABCEGHJKLMNPRSTVXY'.split('')
    const cases = letters.flatMap((letter) => zone.options!.map((option) => ({ postal: `${letter}1A 1A1`, option })))
    const verdicts = serverCheck(cases.map((c) => buildPayload(spec, { ...base, postal_code: c.postal, zone: c.option })))
    const disagreements = cases.flatMap((c, i) => {
      const answers = { ...base, postal_code: c.postal, zone: c.option }
      const pageOk = fieldIssue(zone, c.option, answers) === null
      const serverOk = serverFieldErrors(verdicts[i], 'zone').length === 0
      return pageOk === serverOk ? [] : [`${c.postal} + ${c.option.split(':')[0]}: page ${pageOk}, server ${serverOk}`]
    })
    expect(disagreements).toEqual([])
  })

  it('gives a year-built limit that ends at this year', () => {
    expect(fields.find((f) => f.id === 'year_built')!.max).toBe(new Date().getFullYear())
  })
})

describe.runIf(!HAVE_PYTHON)('the page and the real server agree', () => {
  it.skip(`needs the project's Python at ${PYTHON} (or set RETROFIT_PYTHON)`, () => {})
})
