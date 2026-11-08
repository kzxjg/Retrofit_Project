import { zoneIdFromOption } from './zones'
import type { Answer, Answers, ApiError, BudgetFilter, Field, Package, SortMode, Spec, Weights } from './types'

// Canada Post rules: no D, F, I, O, Q, U anywhere; no W or Z as the first letter
export const POSTAL_RE = /^[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z] ?\d[ABCEGHJ-NPRSTV-Z]\d$/i

export function allFields(spec: Spec): Field[] {
  return spec.sections.flatMap((s) => s.fields)
}

export function isVisible(field: Field, answers: Answers): boolean {
  const cond = field.show_if
  return !cond || answers[cond.field] === cond.equals
}

export function asWeights(value: Answer | undefined): Weights {
  return value && typeof value === 'object' ? value : {}
}

export function isEmpty(value: Answer | undefined): boolean {
  if (value === undefined || value === '') return true
  return typeof value === 'object' && Object.keys(value).length === 0
}

/** The starting answers: every dropdown without a "Select…" choice and every slider at its default. */
export function initialAnswers(spec: Spec): Answers {
  const answers: Answers = {}
  for (const field of allFields(spec)) {
    if (field.type === 'weights') answers[field.id] = defaultWeights(field)
    // a question that others depend on (the preference setting) always has an answer
    else if (field.type === 'select' && allFields(spec).some((f) => f.show_if?.field === field.id)) {
      answers[field.id] = field.options?.[0] ?? ''
    }
  }
  return answers
}

export function defaultWeights(field: Field): Weights {
  return Object.fromEntries((field.criteria ?? []).map((c) => [c.id, c.default]))
}

// ---------------------------------------------------------------------------------------------
// Checks that run while the user types. The server repeats every rule and is the authority.
// ---------------------------------------------------------------------------------------------

/** A problem with one answer. `early` problems cannot be fixed by typing more, so they show at
 *  once; the others (too short, too small) wait until the user leaves the box. */
export type FieldIssue = { message: string; early: boolean }

function tidy(n: number, grouping: boolean): string {
  return n.toLocaleString('en-CA', { maximumFractionDigits: 1, useGrouping: grouping })
}

const integerDigits = (n: number) => String(Math.trunc(Math.abs(n))).length

const POSTAL_FIRST = 'ABCEGHJKLMNPRSTVXY' // Canada Post: no D F I O Q U, and no W or Z first
const POSTAL_LETTER = 'ABCEGHJKLMNPRSTVWXYZ'

export function postalIssue(raw: string): FieldIssue | null {
  const chars = raw.replace(/\s+/g, '').toUpperCase()
  for (let i = 0; i < chars.length; i++) {
    const c = chars[i]
    if (i >= 6) return { message: 'A postal code has 6 characters, e.g. N9A 1A1.', early: true }
    if (i % 2 === 0) {
      if (!(i === 0 ? POSTAL_FIRST : POSTAL_LETTER).includes(c)) {
        const not = i === 0 ? 'D, F, I, O, Q, U, W or Z' : 'D, F, I, O, Q or U'
        return { message: `Character ${i + 1} must be a letter (not ${not}), e.g. N9A 1A1.`, early: true }
      }
    } else if (!/\d/.test(c)) {
      return { message: `Character ${i + 1} must be a digit, e.g. N9A 1A1.`, early: true }
    }
  }
  if (chars.length < 6) return { message: 'Enter all 6 characters, e.g. N9A 1A1.', early: false }
  return null
}

function numberIssue(field: Field, value: string): FieldIssue | null {
  const text = value.trim()
  if (text === '') return null
  if (!/^-?\d*\.?\d*$/.test(text)) return { message: 'Enter a number.', early: true }
  if (!/\d/.test(text)) return { message: 'Enter a number.', early: false } // just "-" or "." so far
  const n = Number(text)
  if (!Number.isFinite(n)) return { message: 'Enter a number.', early: true }
  // a bare trailing dot is fine while typing; any digit after the dot (1985.0) is not a whole number
  if (field.integer && (/\.\d/.test(text) || !Number.isInteger(n))) return { message: 'Enter a whole number.', early: true }

  const lo = field.min
  const hi = field.max
  const tooHigh = hi !== undefined && n > hi
  const tooLow = lo !== undefined && n < lo
  if (tooHigh || tooLow) {
    const money = field.type === 'currency'
    const show = (limit: number) => (money ? `$${tidy(limit, true)}` : tidy(limit, false))
    const low = lo !== undefined ? show(lo) : null
    const high = hi !== undefined ? show(hi) : null
    const what = money ? 'an amount' : field.integer ? 'a whole number' : 'a value'
    const message =
      low !== null && high !== null
        ? `Enter ${what} between ${low} and ${high}.`
        : low !== null
          ? `Enter ${what} of at least ${low}.`
          : `Enter ${what} of at most ${high}.`
    if (tooHigh) return { message, early: true } // typing more digits only makes it bigger
    // too small: wait, unless it cannot grow any more (negative, or already as long as the maximum)
    const longest = hi !== undefined ? integerDigits(hi) : Infinity
    return { message, early: n < 0 || integerDigits(n) >= longest }
  }

  return null
}

function weightsIssue(field: Field, value: Answer | undefined): FieldIssue | null {
  const weights = asWeights(value)
  const lo = field.min ?? 0
  const hi = field.max ?? 100
  const ok = (field.criteria ?? []).every((c) => Number.isInteger(weights[c.id]) && weights[c.id] >= lo && weights[c.id] <= hi)
  if (!ok) return { message: `Give each criterion a whole number from ${lo} to ${hi}.`, early: true }
  if (Object.values(weights).every((w) => w === 0)) {
    return { message: 'Give at least one criterion a weight above 0.', early: true }
  }
  return null
}

/** Zone ids that fit the postal code typed so far, or null when it says nothing yet (no usable first letter). */
export function zoneIdsForPostalCode(field: Field, answers: Answers): string[] | null {
  const rule = field.must_match_postal
  if (!rule) return null
  const postal = answers[rule.field]
  const letter = typeof postal === 'string' ? postal.trim().charAt(0).toUpperCase() : ''
  return rule.zones_by_letter[letter] ?? null
}

/** What is wrong with this answer right now, if anything. An empty answer is not an issue here:
 *  a missing required answer is reported separately, once the user tries to move on. */
export function fieldIssue(field: Field, value: Answer | undefined, answers: Answers): FieldIssue | null {
  if (isEmpty(value)) return null
  if (field.type === 'weights') return weightsIssue(field, value)
  if (typeof value !== 'string') return { message: 'Enter an answer.', early: true }
  if (field.format === 'postal_code') return postalIssue(value)
  if (field.must_match_postal) {
    const allowed = zoneIdsForPostalCode(field, answers)
    const id = zoneIdFromOption(value)
    if (allowed && id && !allowed.includes(id)) {
      return { message: 'That climate zone does not occur where your postal code is. Choose a zone for your area.', early: true }
    }
  }
  if (field.type === 'number' || field.type === 'currency') return numberIssue(field, value)
  return null
}

/** Stop impossible characters from being typed, and tidy the postal code as it is typed. */
export function sanitizeInput(field: Field, raw: string): string {
  if (field.format === 'postal_code') {
    const chars = raw.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 6)
    return chars.length > 3 ? `${chars.slice(0, 3)} ${chars.slice(3)}` : chars
  }
  if (field.type === 'number' || field.type === 'currency') {
    let text = raw.replace(/[^0-9.-]/g, '')
    const negative = text.startsWith('-')
    text = text.replace(/-/g, '')
    const dot = text.indexOf('.')
    if (dot >= 0) text = text.slice(0, dot + 1) + text.slice(dot + 1).replace(/\./g, '')
    return (negative ? '-' : '') + text
  }
  return raw
}

/** Everything that still needs attention before the answers can be sent (in the given questions,
 *  or the whole form). */
export function validate(spec: Spec, answers: Answers, fields: Field[] = allFields(spec)): ApiError[] {
  const problems: ApiError[] = []
  for (const field of fields) {
    if (!isVisible(field, answers)) continue
    const value = answers[field.id]
    if (isEmpty(value)) {
      if (field.required) problems.push({ field: field.id, message: `${field.label} is required.` })
      continue
    }
    const issue = fieldIssue(field, value, answers)
    if (issue) problems.push({ field: field.id, message: issue.message })
  }
  return problems
}

/** The JSON the server expects: visible, answered fields only; numbers as numbers. */
export function buildPayload(spec: Spec, answers: Answers): Record<string, unknown> {
  const payload: Record<string, unknown> = {}
  for (const field of allFields(spec)) {
    if (!isVisible(field, answers)) continue
    const value = answers[field.id]
    if (isEmpty(value)) continue

    if (field.type === 'weights') {
      const weights = asWeights(value)
      payload[field.id] = Object.fromEntries((field.criteria ?? []).map((c) => [c.id, weights[c.id]]))
    } else if (typeof value !== 'string') {
      continue
    } else if (field.type === 'number' || field.type === 'currency') {
      payload[field.id] = Number(value.trim())
    } else {
      payload[field.id] = field.format === 'postal_code' ? value.trim().toUpperCase() : value.trim()
    }
  }
  return payload
}

/** "1980–1989" for a typed year, or null while it is not a usable year. */
export function decadeLabel(value: Answer | undefined): string | null {
  if (typeof value !== 'string' || !/^\d{4}$/.test(value.trim())) return null
  const start = Math.floor(Number(value) / 10) * 10
  return `${start}–${start + 9}`
}

export function money(n: number): string {
  return `$${Math.round(n).toLocaleString('en-CA')}`
}

/** The packages in the order and selection the user asked for. The server sends them best match first. */
export function arrangePackages(packages: Package[], sort: SortMode, filter: BudgetFilter): Package[] {
  const shown = filter === 'within' ? packages.filter((p) => p.within_budget) : [...packages]
  const by: Record<SortMode, (a: Package, b: Package) => number> = {
    personal: (a, b) => b.score - a.score,
    cost: (a, b) => a.cost - b.cost,
    savings: (a, b) => b.saving_pct - a.saving_pct,
    carbon: (a, b) => b.carbon_t - a.carbon_t,
    payback: (a, b) => a.payback_yrs - b.payback_yrs,
  }
  return shown.sort(by[sort])
}
