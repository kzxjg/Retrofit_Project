import { zoneIdFromOption } from './zones'
import type { Answer, Answers, ApiError, Field, Renovation, Spec } from './types'

// Canada Post rules: no D, F, I, O, Q, U anywhere; no W or Z as the first letter
export const POSTAL_RE = /^[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z] ?\d[ABCEGHJ-NPRSTV-Z]\d$/i

export function allFields(spec: Spec): Field[] {
  return spec.sections.flatMap((s) => s.fields)
}

export function isVisible(field: Field, answers: Answers): boolean {
  const cond = field.show_if
  return !cond || answers[cond.field] === cond.equals
}

export function asStrings(value: Answer | undefined): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : []
}

export function asRecords(value: Answer | undefined): Renovation[] {
  return Array.isArray(value) ? value.filter((v): v is Renovation => typeof v === 'object') : []
}

export function isEmpty(value: Answer | undefined): boolean {
  return value === undefined || value === '' || (Array.isArray(value) && value.length === 0)
}

/** A dropdown option as the user should read it: some options (floor area) are shown in the chosen units. */
export function optionLabel(field: Field, spec: Spec, answers: Answers, option: string): string {
  const chosen = answers[spec.unit_field]
  const labels = typeof chosen === 'string' ? field.labels_by_unit?.[chosen] : undefined
  const index = (field.options ?? []).indexOf(option)
  return labels && index >= 0 && labels[index] ? labels[index] : option
}

/** The number a typed or chosen answer stands for (a dropdown option may stand for one), or null. */
function numberOf(field: Field | undefined, value: Answer | undefined): number | null {
  if (typeof value !== 'string' || value.trim() === '') return null
  const mapped = field?.numeric?.[value]
  const n = mapped !== undefined ? mapped : Number(value.trim())
  return Number.isFinite(n) ? n : null
}

/** For a typed number with named ranges (the year built), the name of the range it falls in. */
export function rangeLabel(field: Field, value: Answer | undefined): string | null {
  if (!field.ranges || typeof value !== 'string' || value.trim() === '') return null
  const n = Number(value.trim())
  if (!Number.isInteger(n)) return null
  const hit = field.ranges.find((r) => (r.min === null || n >= r.min) && (r.max === null || n <= r.max))
  return hit ? hit.label : null
}

/** The unit text shown next to a number, from the chosen unit system. */
export function unitSuffix(field: Field, spec: Spec, answers: Answers): string {
  if (field.type === 'currency') return 'CAD'
  if (field.unit_kind === 'power') return 'kW'
  if (field.unit_kind === 'area' || field.unit_kind === 'temperature' || field.unit_kind === 'length') {
    const chosen = answers[spec.unit_field]
    const systems = spec.unit_systems
    const key = typeof chosen === 'string' && chosen in systems ? chosen : Object.keys(systems)[0]
    return systems[key][field.unit_kind]
  }
  return ''
}

// ---------------------------------------------------------------------------------------------
// Checks that run while the user types. The server repeats every rule and is the authority.
// ---------------------------------------------------------------------------------------------

/** A problem with one answer. `early` problems cannot be fixed by typing more, so they show at
 *  once; the others (too short, too small) wait until the user leaves the box. */
export type FieldIssue = { message: string; early: boolean }

const AREA_M2_PER_FT2 = 0.09290304 // the same factor the server uses

export function isImperial(spec: Spec, answers: Answers): boolean {
  const chosen = answers[spec.unit_field]
  return typeof chosen === 'string' && chosen.startsWith('Imperial')
}

/** The limits in the spec are in metric. Convert a typed value to metric to compare. */
function toMetric(field: Field, value: number, imperial: boolean): number {
  if (imperial && field.unit_kind === 'area') return value * AREA_M2_PER_FT2
  if (imperial && field.unit_kind === 'temperature') return ((value - 32) * 5) / 9
  if (imperial && field.unit_kind === 'length') return value * 25.4 // inches to millimetres
  return value
}

/** ...and convert a limit to the units the user chose, so the message speaks their units. */
function fromMetric(field: Field, value: number, imperial: boolean): number {
  if (imperial && field.unit_kind === 'area') return value / AREA_M2_PER_FT2
  if (imperial && field.unit_kind === 'temperature') return (value * 9) / 5 + 32
  if (imperial && field.unit_kind === 'length') return value / 25.4
  return value
}

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

function numberIssue(field: Field, value: string, spec: Spec, answers: Answers): FieldIssue | null {
  const text = value.trim()
  if (text === '') return null
  if (!/^-?\d*\.?\d*$/.test(text)) return { message: 'Enter a number.', early: true }
  if (!/\d/.test(text)) return { message: 'Enter a number.', early: false } // just "-" or "." so far
  const n = Number(text)
  if (!Number.isFinite(n)) return { message: 'Enter a number.', early: true }
  // a bare trailing dot is fine while typing; any digit after the dot (1985.0) is not a whole number
  if (field.integer && (/\.\d/.test(text) || !Number.isInteger(n))) return { message: 'Enter a whole number.', early: true }

  const imperial = isImperial(spec, answers)
  const metric = toMetric(field, n, imperial)
  const lo = field.min
  const hi = field.max
  const tooHigh = hi !== undefined && metric > hi
  const tooLow = lo !== undefined && metric < lo
  if (tooHigh || tooLow) {
    const unit = unitSuffix(field, spec, answers)
    const money = field.type === 'currency'
    const show = (limit: number, round: (x: number) => number) => {
      const shown = round(fromMetric(field, limit, imperial) * 10) / 10
      return money ? `$${tidy(shown, true)}` : tidy(shown, false)
    }
    const low = lo !== undefined ? show(lo, Math.ceil) : null
    const high = hi !== undefined ? show(hi, Math.floor) : null
    const what = money ? 'an amount' : field.integer ? 'a whole number' : 'a value'
    const tail = unit ? ` ${unit}` : ''
    const message =
      low !== null && high !== null
        ? `Enter ${what} between ${low} and ${high}${tail}.`
        : low !== null
          ? `Enter ${what} of at least ${low}${tail}.`
          : `Enter ${what} of at most ${high}${tail}.`
    if (tooHigh) return { message, early: true } // typing more digits only makes it bigger
    // too small: wait, unless it cannot grow any more (negative, or already as long as the maximum)
    const longest = hi !== undefined ? integerDigits(fromMetric(field, hi, imperial)) : Infinity
    return { message, early: n < 0 || integerDigits(n) >= longest }
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
 *  a missing required answer is reported separately, once the user tries to submit. */
export function fieldIssue(field: Field, value: Answer | undefined, spec: Spec, answers: Answers): FieldIssue | null {
  if (isEmpty(value)) return null
  const rule = field.not_more_than
  if (rule) {
    const mine = numberOf(field, value)
    const other = numberOf(allFields(spec).find((f) => f.id === rule.field), answers[rule.field])
    if (mine !== null && other !== null && mine > other) return { message: rule.message, early: false }
  }
  if (field.format === 'postal_code' && typeof value === 'string') return postalIssue(value)
  if (field.must_match_postal && typeof value === 'string') {
    const allowed = zoneIdsForPostalCode(field, answers)
    const id = zoneIdFromOption(value)
    if (allowed && id && !allowed.includes(id)) {
      return { message: 'That climate zone does not occur where your postal code is. Choose a zone for your area.', early: true }
    }
  }
  if ((field.type === 'number' || field.type === 'currency') && typeof value === 'string') {
    return numberIssue(field, value, spec, answers)
  }
  if (field.type === 'records') {
    const records = asRecords(value)
    for (let i = 0; i < records.length; i++) {
      const hasType = records[i].type.trim() !== ''
      const hasYear = records[i].year !== ''
      if (hasType !== hasYear) {
        return { message: `Renovation ${i + 1}: enter both a type and a year, or remove it.`, early: false }
      }
      const built = Number(answers.year_built)
      if (hasYear && Number.isInteger(built) && Number(records[i].year) < built) {
        return { message: `Renovation ${i + 1} is dated before the building was built (${built}).`, early: true }
      }
    }
  }
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

/** Everything that still needs attention before the form can be sent. */
export function validate(spec: Spec, answers: Answers): ApiError[] {
  const problems: ApiError[] = []
  for (const field of allFields(spec)) {
    if (!isVisible(field, answers)) continue
    const value = answers[field.id]
    if (isEmpty(value)) {
      if (field.required) problems.push({ field: field.id, message: `${field.label} is required.` })
      continue
    }
    const issue = fieldIssue(field, value, spec, answers)
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

    if (field.type === 'number' || field.type === 'currency') {
      payload[field.id] = Number(String(value).trim())
    } else if (field.type === 'records') {
      const records = asRecords(value)
        .filter((r) => r.type.trim() !== '' && r.year !== '')
        .map((r) => ({ type: r.type.trim(), year: Number(r.year) }))
      if (records.length) payload[field.id] = records
    } else if (field.type === 'checklist' || field.type === 'multiselect' || field.type === 'incentives') {
      payload[field.id] = asStrings(value)
    } else if (typeof value === 'string') {
      payload[field.id] = field.format === 'postal_code' ? value.trim().toUpperCase() : value.trim()
    }

    if (field.other_text && asStrings(value).includes('Other')) {
      const other = answers[`${field.id}_other`]
      if (typeof other === 'string' && other.trim()) payload[`${field.id}_other`] = other.trim()
    }
  }
  return payload
}

/** How an answer reads in the review step. */
export function displayValue(field: Field, value: Answer | undefined, spec: Spec, answers: Answers): string {
  if (field.type === 'records') {
    return asRecords(value)
      .filter((r) => r.type.trim() !== '' && r.year !== '')
      .map((r) => `${r.type.trim()} (${r.year})`)
      .join('; ')
  }
  if (Array.isArray(value)) {
    const parts = asStrings(value)
    const other = answers[`${field.id}_other`]
    if (field.other_text && parts.includes('Other') && typeof other === 'string' && other.trim()) {
      return parts.map((p) => (p === 'Other' ? `Other: ${other.trim()}` : p)).join(', ')
    }
    return parts.join(', ')
  }
  const text = typeof value === 'string' ? value : ''
  if (!text) return ''
  if (field.type === 'select') return optionLabel(field, spec, answers, text)
  if (field.type === 'currency') return `$${text} CAD`
  const range = rangeLabel(field, value)
  if (range) return `${text} (${range})`
  const suffix = field.type === 'number' ? unitSuffix(field, spec, answers) : ''
  return suffix ? `${text} ${suffix}` : text
}
