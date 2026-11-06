import { allFields, displayValue, isEmpty, isVisible } from './formLogic'
import type { Answers, ApiError, Spec } from './types'

type Props = {
  spec: Spec
  answers: Answers
  problems: ApiError[] // everything that still needs attention
  showProblems: boolean // only after the first attempt to submit
  sectionNumber: number
}

export default function Review({ spec, answers, problems, showProblems, sectionNumber }: Props) {
  const labelFor = (id: string) => allFields(spec).find((f) => f.id === id)?.label ?? ''

  return (
    <section className="pg-box" aria-labelledby="review-title">
      <p className="pg-label">SECTION {sectionNumber}</p>
      <h2 id="review-title" className="pg-section-title">
        Data review and validation
      </h2>

      {spec.sections.map((section) => {
        const rows = section.fields.filter(
          (f) => isVisible(f, answers) && !isEmpty(answers[f.id]) && displayValue(f, answers[f.id], spec, answers),
        )
        if (rows.length === 0) return null
        return (
          <div key={section.id} className="pg-review-group">
            <h3>{section.title}</h3>
            <dl className="pg-review">
              {rows.map((f) => (
                <div key={f.id} className="pg-review-row">
                  <dt>{f.label}</dt>
                  <dd>{displayValue(f, answers[f.id], spec, answers)}</dd>
                </div>
              ))}
            </dl>
          </div>
        )
      })}

      {showProblems && problems.length > 0 ? (
        <div className="pg-alert pg-alert--error" role="alert">
          <strong>Please fix the following:</strong>
          <ul>
            {problems.map((p, i) => (
              <li key={`${p.field}-${i}`}>
                {p.message.startsWith(labelFor(p.field)) || !labelFor(p.field)
                  ? p.message
                  : `${labelFor(p.field)}: ${p.message}`}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="pg-help" aria-live="polite">
          {problems.length === 0
            ? 'Everything required is filled in. Check your answers, then submit.'
            : `${problems.length} item${problems.length === 1 ? '' : 's'} still need an answer.`}
        </p>
      )}
    </section>
  )
}
