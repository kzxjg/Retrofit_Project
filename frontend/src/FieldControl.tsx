import { asWeights, sanitizeInput, zoneIdsForPostalCode } from './formLogic'
import { zoneIdFromOption } from './zones'
import type { Answer, Answers, Field } from './types'

type Props = {
  field: Field
  answers: Answers
  onChange: (id: string, value: Answer) => void
  error?: string | null // what is wrong with this answer, shown right under it
  onBlur?: () => void // called when the user leaves the question
}

// A climate zone question only offers the zones that occur where the postal code is (the chosen one
// stays listed so its error can be shown).
function fitsPostalCode(field: Field, answers: Answers, option: string, chosen: Answer | undefined): boolean {
  const allowed = zoneIdsForPostalCode(field, answers)
  if (!allowed || option === chosen) return true
  const id = zoneIdFromOption(option)
  return !id || allowed.includes(id)
}

// The question, with its problem (if any) shown directly under it.
export default function FieldControl(props: Props) {
  return (
    <div className="pg-field">
      <Control {...props} />
      {props.error && (
        <p className="pg-error" id={`f-${props.field.id}-error`}>
          {props.error}
        </p>
      )}
    </div>
  )
}

function Control({ field, answers, onChange, error, onBlur }: Props) {
  const value = answers[field.id]
  const id = `f-${field.id}`
  const help = field.help ? (
    <p className="pg-help" id={`${id}-help`}>
      {field.help}
    </p>
  ) : null
  const described = [field.help ? `${id}-help` : null, error ? `${id}-error` : null].filter(Boolean).join(' ') || undefined
  const invalid = error ? true : undefined

  switch (field.type) {
    case 'text':
    case 'number':
    case 'currency': {
      const isNumeric = field.type !== 'text'
      return (
        <>
          <label htmlFor={id} className="pg-field-title">
            {field.label}
          </label>
          <input
            id={id}
            type="text"
            inputMode={isNumeric ? (field.integer ? 'numeric' : 'decimal') : undefined}
            maxLength={field.format === 'postal_code' ? 7 : undefined}
            className={(field.format === 'postal_code' ? 'pg-input pg-input--postal' : 'pg-input') + (error ? ' pg-input--invalid' : '')}
            placeholder={field.placeholder}
            value={typeof value === 'string' ? value : ''}
            aria-invalid={invalid}
            aria-describedby={described}
            onChange={(e) => onChange(field.id, sanitizeInput(field, e.target.value))}
            onBlur={onBlur}
          />
          {help}
        </>
      )
    }

    case 'select': {
      const options = field.options ?? []
      const chosen = typeof value === 'string' ? value : ''
      return (
        <>
          <label htmlFor={id} className="pg-field-title">
            {field.label}
          </label>
          <select
            id={id}
            className={error ? 'pg-select pg-select--invalid' : 'pg-select'}
            value={chosen}
            aria-invalid={invalid}
            aria-describedby={described}
            onChange={(e) => onChange(field.id, e.target.value)}
            onBlur={onBlur}
          >
            {/* questions with an answer from the start (the preference setting) have no blank choice */}
            {!options.includes(chosen) && <option value="">Select…</option>}
            {options.filter((o) => fitsPostalCode(field, answers, o, value)).map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
          {/* a long answer is cut off inside the closed dropdown, so show it in full as text */}
          {options.some((o) => o.length > 40) && <p className="pg-selected pg-selected--reserved">{chosen}</p>}
          {help}
        </>
      )
    }

    case 'weights': {
      const weights = asWeights(value)
      const lo = field.min ?? 0
      const hi = field.max ?? 100
      return (
        <fieldset className="pg-group" aria-describedby={described}>
          <legend className="pg-field-title">{field.label}</legend>
          {help}
          {(field.criteria ?? []).map((c) => {
            const current = weights[c.id] ?? c.default
            return (
              <div key={c.id} className="pg-range">
                <label htmlFor={`${id}-${c.id}`}>{c.label}</label>
                <input
                  id={`${id}-${c.id}`}
                  type="range"
                  min={lo}
                  max={hi}
                  step={1}
                  value={current}
                  onChange={(e) => onChange(field.id, { ...weights, [c.id]: Number(e.target.value) })}
                  onBlur={onBlur}
                />
                <strong aria-hidden="true">{current}</strong>
              </div>
            )
          })}
        </fieldset>
      )
    }

    default:
      return null
  }
}
