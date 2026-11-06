import type { Field, Renovation } from './types'

type Props = {
  field: Field
  records: Renovation[]
  onChange: (next: Renovation[]) => void
}

export default function Renovations({ field, records, onChange }: Props) {
  const [firstYear, lastYear] = field.year_range ?? [1900, new Date().getFullYear()]
  const years: number[] = []
  for (let y = lastYear; y >= firstYear; y--) years.push(y)
  const max = field.max_records ?? 20

  function update(index: number, change: Partial<Renovation>) {
    onChange(records.map((r, i) => (i === index ? { ...r, ...change } : r)))
  }

  return (
    <fieldset className="pg-group">
      <legend className="pg-field-title">{field.label}</legend>
      {field.help && <p className="pg-help">{field.help}</p>}

      {records.map((record, i) => (
        <div key={i} className="pg-record">
          <div>
            <label htmlFor={`${field.id}-${i}-type`} className="pg-sub-title">
              Renovation {i + 1} {field.type_options ? 'building element' : 'type'}
            </label>
            {field.type_options ? (
              <select
                id={`${field.id}-${i}-type`}
                className="pg-select"
                value={record.type}
                onChange={(e) => update(i, { type: e.target.value })}
              >
                <option value="">Select…</option>
                {field.type_options.map((element) => (
                  <option key={element} value={element}>
                    {element}
                  </option>
                ))}
              </select>
            ) : (
              <input
                id={`${field.id}-${i}-type`}
                type="text"
                className="pg-input"
                maxLength={100}
                placeholder="e.g. New roof"
                value={record.type}
                onChange={(e) => update(i, { type: e.target.value })}
              />
            )}
          </div>
          <div>
            <label htmlFor={`${field.id}-${i}-year`} className="pg-sub-title">
              Renovation {i + 1} year
            </label>
            <select
              id={`${field.id}-${i}-year`}
              className="pg-select"
              value={record.year}
              onChange={(e) => update(i, { year: e.target.value })}
            >
              <option value="">Select…</option>
              {years.map((y) => (
                <option key={y} value={String(y)}>
                  {y}
                </option>
              ))}
            </select>
          </div>
          <button
            type="button"
            className="pg-secondary"
            aria-label={`Remove renovation ${i + 1}`}
            onClick={() => onChange(records.filter((_, n) => n !== i))}
          >
            Remove
          </button>
        </div>
      ))}

      <button
        type="button"
        className="pg-secondary"
        disabled={records.length >= max}
        onClick={() => onChange([...records, { type: '', year: '' }])}
      >
        Add renovation
      </button>
    </fieldset>
  )
}
