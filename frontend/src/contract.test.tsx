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
import { allFields, buildPayload, fieldIssue, validate } from './formLogic'
import { optionForZoneId } from './zones'
import type { Answer, Answers, ApiError, Field, Spec } from './types'

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

type Verdict = { errors: ApiError[]; package: string | null }
const serverCheck = (payloads: Record<string, unknown>[]) => python('check', payloads) as Verdict[]

// The question types the page knows how to draw (FieldControl.tsx and types.ts).
const PAGE_TYPES = ['text', 'select', 'radio', 'number', 'currency', 'checklist', 'multiselect', 'records', 'incentives']

// Limits in the spec are metric; a typed answer is in the units chosen.
function inUnits(f: Field, metric: number, imperial: boolean): number {
  if (!imperial) return metric
  if (f.unit_kind === 'area') return metric / 0.09290304
  if (f.unit_kind === 'temperature') return (metric * 9) / 5 + 32
  if (f.unit_kind === 'length') return metric / 25.4
  return metric
}

/** A complete set of answers, typed the way the page stores them (numbers as text, records as text). */
function sampleAnswers(spec: Spec, units?: string): Answers {
  const answers: Answers = {}
  const imperial = Boolean(units?.startsWith('Imperial'))
  for (const f of allFields(spec)) {
    let value: Answer
    switch (f.type) {
      case 'select':
      case 'radio':
        value = f.options![0]
        break
      case 'checklist':
      case 'multiselect':
        value = [f.options!.find((o) => o !== 'Other')!]
        break
      case 'number':
      case 'currency':
        value = String(Math.ceil(inUnits(f, f.min !== undefined && f.min >= 1 ? f.min : 1, imperial)))
        break
      case 'records':
        value = [{ type: f.type_options?.[0] ?? 'Window replacement', year: String(f.year_range![1]) }]
        break
      case 'incentives':
        value = []
        break
      default:
        value = f.format === 'postal_code' ? 'N9A 1A1' : 'text'
    }
    answers[f.id] = value
  }
  const zone = allFields(spec).find((f) => f.id === 'zone')!
  answers.zone = optionForZoneId(zone.options!, zone.must_match_postal!.zones_by_letter.N[0])!
  if (units) answers[spec.unit_field] = units
  return answers
}

const serverFieldErrors = (verdict: Verdict, id: string) => verdict.errors.filter((e) => e.field === id)

afterEach(() => vi.unstubAllGlobals())

describe.skipIf(!HAVE_PYTHON)('the page and the real server agree', () => {
  const spec = HAVE_PYTHON ? (python('spec') as Spec) : ({ sections: [] } as unknown as Spec)
  const fields = allFields(spec)

  it('uses only question types the page can draw', () => {
    const unknown = fields.filter((f) => !PAGE_TYPES.includes(f.type)).map((f) => `${f.id}: ${f.type}`)
    expect(unknown).toEqual([])
  })

  it('draws every question of the real form', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => spec })))
    render(<App />)
    await screen.findByRole('button', { name: /get my recommendation/i })
    const text = document.body.textContent ?? ''
    const missing = fields.filter((f) => !f.show_if && !text.includes(f.label)).map((f) => f.id)
    expect(missing).toEqual([])
    for (const section of spec.sections) {
      if (section.fields.some((f) => !f.placement && !f.show_if)) {
        expect(screen.getByRole('heading', { name: section.title })).toBeTruthy()
      }
    }
  })

  it('has follow-up questions whose conditions can actually be met', () => {
    for (const f of fields.filter((x) => x.show_if)) {
      const parent = fields.find((x) => x.id === f.show_if!.field)
      expect(parent, `${f.id} depends on a missing question`).toBeDefined()
      expect(parent!.options ?? [], `${f.id} waits for an answer ${parent!.id} never offers`).toContain(f.show_if!.equals)
    }
  })

  it('links questions only to questions that exist', () => {
    for (const f of fields) {
      if (f.not_more_than) expect(fields.some((x) => x.id === f.not_more_than!.field), f.id).toBe(true)
      if (f.must_match_postal) expect(fields.some((x) => x.id === f.must_match_postal!.field), f.id).toBe(true)
      expect(spec.unit_systems).toBeDefined()
    }
    expect(fields.some((f) => f.id === spec.unit_field)).toBe(true)
  })

  it.each([['metric', 0], ['imperial', 1]])(
    'sends a complete %s form in a shape the server accepts and gets a package back',
    (_, unitIndex) => {
      const units = Object.keys(spec.unit_systems)[unitIndex]
      const answers = sampleAnswers(spec, units)
      expect(validate(spec, answers)).toEqual([])
      const [verdict] = serverCheck([buildPayload(spec, answers)])
      expect(verdict.errors).toEqual([])
      expect(verdict.package).toEqual(expect.any(String))
    },
  )

  it('sends only questions the server knows', () => {
    const answers = sampleAnswers(spec)
    for (const f of fields) if (f.show_if) answers[f.show_if.field] = f.show_if.equals // show every follow-up
    const payload = buildPayload(spec, answers)
    const [verdict] = serverCheck([payload])
    expect(verdict.errors.filter((e) => /unknown field/i.test(e.message))).toEqual([])
  })

  it.each([['metric', 0], ['imperial', 1]])('agrees with the server on the limits of every typed number in %s', (_, unitIndex) => {
    const units = Object.keys(spec.unit_systems)[unitIndex]
    const imperial = units.startsWith('Imperial')
    const base = sampleAnswers(spec, units)
    const cases: { field: Field; typed: string }[] = []
    for (const f of fields.filter((x) => x.type === 'number' || x.type === 'currency')) {
      const step = f.integer ? 1 : 0.5
      // the limits as the user would type them: rounded inwards to one decimal (whole numbers if asked)
      const scale = f.integer ? 1 : 10
      const values = new Set<number>([1])
      if (f.min !== undefined) {
        const lo = Math.ceil(inUnits(f, f.min, imperial) * scale) / scale
        ;[lo, lo - step].forEach((v) => values.add(v))
      }
      if (f.max !== undefined) {
        const hi = Math.floor(inUnits(f, f.max, imperial) * scale) / scale
        ;[hi, hi + step].forEach((v) => values.add(v))
      }
      for (const v of values) cases.push({ field: f, typed: String(v) })
    }
    const payloads = cases.map(({ field, typed }) => buildPayload(spec, { ...base, [field.id]: typed }))
    const verdicts = serverCheck(payloads)
    const disagreements = cases.flatMap(({ field, typed }, i) => {
      const answers = { ...base, [field.id]: typed }
      const pageOk = fieldIssue(field, typed, spec, answers) === null
      const serverOk = serverFieldErrors(verdicts[i], field.id).length === 0
      return pageOk === serverOk ? [] : [`${field.id}=${typed}: page ${pageOk ? 'accepts' : 'refuses'}, server ${serverOk ? 'accepts' : 'refuses'}`]
    })
    expect(disagreements).toEqual([])
  })

  it('agrees with the server on which climate zones fit each postal code letter', () => {
    const zone = fields.find((f) => f.id === 'zone')!
    const base = sampleAnswers(spec)
    const letters = 'ABCEGHJKLMNPRSTVXY'.split('')
    const cases = letters.flatMap((letter) => zone.options!.map((option) => ({ postal: `${letter}1A 1A1`, option })))
    const verdicts = serverCheck(cases.map((c) => buildPayload(spec, { ...base, postal_code: c.postal, zone: c.option })))
    const disagreements = cases.flatMap((c, i) => {
      const answers = { ...base, postal_code: c.postal, zone: c.option }
      const pageOk = fieldIssue(zone, c.option, spec, answers) === null
      const serverOk = serverFieldErrors(verdicts[i], 'zone').length === 0
      return pageOk === serverOk ? [] : [`${c.postal} + ${c.option.split(':')[0]}: page ${pageOk}, server ${serverOk}`]
    })
    expect(disagreements).toEqual([])
  })

  it('agrees with the server on renovations dated before the building', () => {
    const base = sampleAnswers(spec)
    const records = fields.find((f) => f.type === 'records')!
    // a year built inside the range renovations can be dated in, so only the order is tested
    const built = Math.max(Number(base.year_built), records.year_range![0] + 5)
    const cases = [built - 1, built, built + 1].map((year) => ({
      ...base,
      year_built: String(built),
      [records.id]: [{ type: records.type_options?.[0] ?? 'Window replacement', year: String(year) }],
    }))
    const verdicts = serverCheck(cases.map((a) => buildPayload(spec, a)))
    cases.forEach((answers, i) => {
      const pageOk = fieldIssue(records, answers[records.id], spec, answers) === null
      expect(serverFieldErrors(verdicts[i], records.id).length === 0, `year ${built - 1 + i}`).toBe(pageOk)
    })
  })

  it("gives renovation and year-built limits that end at this year", () => {
    const thisYear = new Date().getFullYear()
    const records = fields.find((f) => f.type === 'records')!
    expect(records.year_range![1]).toBe(thisYear)
    expect(fields.find((f) => f.id === 'year_built')!.max).toBe(thisYear)
  })
})

describe.runIf(!HAVE_PYTHON)('the page and the real server agree', () => {
  it.skip(`needs the project's Python at ${PYTHON} (or set RETROFIT_PYTHON)`, () => {})
})
