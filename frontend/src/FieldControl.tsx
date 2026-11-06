import Incentives from './Incentives'
import Renovations from './Renovations'
import { asRecords, asStrings, zoneIdsForPostalCode, optionLabel, rangeLabel, sanitizeInput, unitSuffix } from './formLogic'
import { zoneIdFromOption } from './zones'
import type { Answer, Answers, Field, Spec } from './types'

type Props = {
  field: Field
  spec: Spec
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

function toggle(list: string[], option: string): string[] {
  return list.includes(option) ? list.filter((o) => o !== option) : [...list, option]
}

// The question, with its problem (if any) shown directly under it.
export default function FieldControl(props: Props) {
  return (
    <>
      <Control {...props} />
      {props.error && (
        <p className="pg-error" id={`f-${props.field.id}-error`}>
          {props.error}
        </p>
      )}
    </>
  )
}

function Control({ field, spec, answers, onChange, error, onBlur }: Props) {
  const value = answers[field.id]
  const id = `f-${field.id}`
  const suffix = unitSuffix(field, spec, answers)
  const isNumeric = field.type === 'number' || field.type === 'currency'
  const label = isNumeric && suffix ? `${field.label} (${suffix})` : field.label
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
    case 'currency':
      return (
        <div className="pg-field">
          <label htmlFor={id} className="pg-field-title">
            {label}
          </label>
          <input
            id={id}
            type="text"
            inputMode={isNumeric ? 'decimal' : undefined}
            maxLength={field.format === 'postal_code' ? 7 : undefined}
            className={(field.format === 'postal_code' ? 'pg-input pg-input--postal' : 'pg-input') + (error ? ' pg-input--invalid' : '')}
            placeholder={field.placeholder}
            value={typeof value === 'string' ? value : ''}
            aria-invalid={invalid}
            aria-describedby={described}
            onChange={(e) => onChange(field.id, sanitizeInput(field, e.target.value))}
            onBlur={onBlur}
          />
          {/* e.g. under a typed year: the generation it falls in */}
          {!error && rangeLabel(field, value) && <p className="pg-selected">{rangeLabel(field, value)}</p>}
          {help}
        </div>
      )

    case 'select':
      return (
        <div className="pg-field">
          <label htmlFor={id} className="pg-field-title">
            {label}
          </label>
          <select
            id={id}
            className={error ? 'pg-select pg-select--invalid' : 'pg-select'}
            value={typeof value === 'string' ? value : ''}
            aria-invalid={invalid}
            aria-describedby={described}
            onChange={(e) => onChange(field.id, e.target.value)}
            onBlur={onBlur}
          >
            <option value="">Select…</option>
            {(field.options ?? []).filter((o) => fitsPostalCode(field, answers, o, value)).map((o) => (
              <option key={o} value={o}>
                {optionLabel(field, spec, answers, o)}
              </option>
            ))}
          </select>
          {/* a long answer is cut off inside the closed dropdown, so show it in full as text */}
          {(field.options ?? []).some((o) => o.length > 40) && (
            <p className="pg-selected pg-selected--reserved">{typeof value === 'string' ? value : ''}</p>
          )}
          {help}
        </div>
      )

    case 'radio':
      return (
        <fieldset className="pg-group pg-field--wide">
          <legend className="pg-field-title">{label}</legend>
          <div className="pg-choices">
            {(field.options ?? []).map((o) => (
              <label key={o} className="pg-choice">
                <input
                  type="radio"
                  name={field.id}
                  value={o}
                  checked={value === o}
                  onChange={() => onChange(field.id, o)}
                />
                {o}
              </label>
            ))}
          </div>
          {help}
        </fieldset>
      )

    case 'checklist':
    case 'multiselect': {
      const chosen = asStrings(value)
      const options = (field.options ?? []).map((o) => (
        <label key={o} className="pg-choice">
          <input
            type="checkbox"
            checked={chosen.includes(o)}
            onChange={() => onChange(field.id, toggle(chosen, o))}
          />
          {o}
        </label>
      ))
      return (
        <fieldset className={field.type === 'checklist' ? 'pg-group pg-field--wide' : 'pg-group'}>
          <legend className="pg-field-title">{label}</legend>
          {field.type === 'checklist' && help}
          {field.type === 'checklist' ? (
            <div className="pg-choices pg-choices--column">{options}</div>
          ) : (
            <details className="pg-ms">
              <summary>{chosen.length ? `${chosen.length} selected: ${chosen.join(', ')}` : 'Select…'}</summary>
              <div className="pg-choices pg-choices--column">{options}</div>
            </details>
          )}
          {field.type === 'multiselect' && help}
          {field.other_text && chosen.includes('Other') && (
            <div className="pg-other">
              <label htmlFor={`${id}-other`} className="pg-sub-title">
                {field.label}: other (please specify)
              </label>
              <input
                id={`${id}-other`}
                type="text"
                className="pg-input"
                maxLength={200}
                value={typeof answers[`${field.id}_other`] === 'string' ? (answers[`${field.id}_other`] as string) : ''}
                onChange={(e) => onChange(`${field.id}_other`, e.target.value)}
              />
            </div>
          )}
        </fieldset>
      )
    }

    case 'records':
      return (
        <div className="pg-field--wide" onBlur={onBlur}>
          <Renovations
            field={field}
            records={asRecords(value)}
            onChange={(next) => onChange(field.id, next)}
          />
        </div>
      )

    case 'incentives': {
      const zone = typeof answers.zone === 'string' ? answers.zone : ''
      return (
        <div className="pg-field--wide">
          <Incentives
            field={field}
            zone={zone}
            selected={asStrings(value)}
            onChange={(next) => onChange(field.id, next)}
          />
        </div>
      )
    }

    default:
      return null
  }
}
