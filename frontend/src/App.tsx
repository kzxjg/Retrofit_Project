import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { ServerMessage, fetchSpec, submitAnswers } from './api'
import CanadaMap from './CanadaMap'
import FieldControl from './FieldControl'
import Review from './Review'
import { allFields, buildPayload, fieldIssue, isEmpty, isVisible, validate } from './formLogic'
import { optionForZoneId, zoneIdFromOption } from './zones'
import type { Answer, Answers, ApiError, Field, Spec } from './types'
import './App.css'

const WIDE_TYPES = ['radio', 'checklist', 'records', 'incentives']





export default function App() {
  const [spec, setSpec] = useState<Spec | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [answers, setAnswers] = useState<Answers>({})
  const [attempted, setAttempted] = useState(false)
  const [touched, setTouched] = useState<Record<string, boolean>>({}) 
  const [serverErrors, setServerErrors] = useState<ApiError[]>([])
  const [serverError, setServerError] = useState<string | null>(null)
  const [recommendation, setRecommendation] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    fetchSpec()
      .then(setSpec)
      .catch((err: unknown) =>
        setLoadError(err instanceof Error ? err.message : 'Could not reach the backend.'),
      )
  }, [])

  function leaveField(id: string) {
    setTouched((prev) => (prev[id] ? prev : { ...prev, [id]: true }))
  }

  function changeField(id: string, value: Answer) {
    setServerErrors((prev) => (prev.some((e) => e.field === id) ? prev.filter((e) => e.field !== id) : prev)) // being edited again
    setAnswers((prev) => {
      const next: Answers = { ...prev, [id]: value }
      if (id === 'zone') next.subsidies = [] 
      return next
    })
  }


  function chooseOnMap(zoneId: string) {
    const options = spec ? allFields(spec).find((f) => f.id === 'zone')?.options : undefined
    const option = options ? optionForZoneId(options, zoneId) : undefined
    if (option) changeField('zone', option)
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!spec) return
    setAttempted(true)
    setRecommendation(null)
    setServerError(null)
    setServerErrors([])
    const found = validate(spec, answers)
    if (found.length > 0) {
      document.getElementById(`f-${found[0].field}`)?.focus() // take the user to the first problem
      return
    }

    setSubmitting(true)
    try {
      const outcome = await submitAnswers(buildPayload(spec, answers))
      if (outcome.ok) setRecommendation(outcome.recommendation)
      else setServerErrors(outcome.errors)
    } catch (err) {
      if (err instanceof ServerMessage) {
        setServerError(err.message) // the server's own wording, e.g. to wait before trying again
      } else {
        const reason = err instanceof Error ? err.message : 'Could not reach the backend.'
        setServerError(`Could not get a recommendation: ${reason}. Is the Django server running?`)
      }
    } finally {
      setSubmitting(false)
    }
  }

  const header = (
    <header className="pg-top">
      <div className="pg-top-inner">
        <span className="pg-brand">Retrofit Decision Tool</span>
      </div>
    </header>
  )

  const footer = (
    <footer className="pg-footer">
      <img className="pg-logo" src="/uwindsor-logo.png" alt="University of Windsor" width={151} height={56} />
    </footer>
  )

  if (!spec) {
    return (
      <div className="pg">
        {header}
        <div className="pg-main">
          {loadError ? (
            <div className="pg-alert pg-alert--error" role="alert">
              Could not load the form: {loadError}. Is the Django server running?
            </div>
          ) : (
            <p className="pg-help">Loading the form…</p>
          )}
        </div>
        {footer}
      </div>
    )
  }



  const errorFor = (f: Field): string | null => {
    if (!isVisible(f, answers)) return null
    const value = answers[f.id]
    if (attempted && f.required && isEmpty(value)) return `${f.label} is required.`
    const issue = fieldIssue(f, value, spec, answers)
    if (issue && (issue.early || touched[f.id] || attempted)) return issue.message
    return serverErrors.find((e) => e.field === f.id)?.message ?? null
  }
  const control = (f: Field) => (
    <FieldControl
      field={f}
      spec={spec}
      answers={answers}
      onChange={changeField}
      error={errorFor(f)}
      onBlur={() => leaveField(f.id)}
    />
  )

  const topFields = allFields(spec).filter((f) => f.placement === 'top')
  const mapFields = allFields(spec).filter((f) => f.placement === 'map')
  const selectedZoneId = typeof answers.zone === 'string' ? zoneIdFromOption(answers.zone) : null
  const clientProblems = validate(spec, answers)
  const problems = [
    ...clientProblems,
    ...serverErrors.filter(
      (s) => !clientProblems.some((c) => c.field === s.field && c.message === s.message),
    ),
  ]

  return (
    <div className="pg">
      {header}

      <div className="pg-main">
        {/* Top row: the basics on the left, the map with the climate zone under it on the right */}
        <div className="pg-start">
          <div className="pg-box">
            <p className="pg-label">YOUR BUILDING</p>
            <div className="pg-start-fields">
              {topFields.map((f) => (
                <div key={f.id} className={WIDE_TYPES.includes(f.type) ? 'pg-start-field pg-start-field--wide' : 'pg-start-field'}>
                  {control(f)}
                </div>
              ))}
              <p className="pg-help pg-start-hint">
                Fill in what you know. Use &quot;Unknown&quot; where a question offers it. You can review
                everything before you submit.
              </p>
            </div>
          </div>
          <div className="pg-box">
            <CanadaMap selectedZoneId={selectedZoneId} onSelectZone={chooseOnMap}>
              {mapFields.map((f) => (
                <div key={f.id} className="pg-under-map">
                  {control(f)}
                </div>
              ))}
            </CanadaMap>
          </div>
        </div>

        <form onSubmit={handleSubmit} noValidate>
          {spec.sections.map((section) => {
            const fields = section.fields.filter((f) => !f.placement && isVisible(f, answers))
            if (fields.length === 0) return null
            return (
              <section key={section.id} className="pg-box" aria-labelledby={`sec-${section.id}`}>
                <h2 id={`sec-${section.id}`} className="pg-section-title">
                  {section.title}
                </h2>
                <div className="pg-fields">
                  {fields.map((f) => (
                    <div key={f.id} className={WIDE_TYPES.includes(f.type) ? 'pg-field--wide' : undefined}>
                      {control(f)}
                    </div>
                  ))}
                </div>
              </section>
            )
          })}

          <Review
            spec={spec}
            answers={answers}
            problems={problems}
            showProblems={attempted}
            sectionNumber={spec.sections.length + 1}
          />

          <button type="submit" className="pg-submit" disabled={submitting}>
            {submitting ? 'Submitting…' : 'Get my recommendation'}
          </button>
        </form>

        {serverError && (
          <div className="pg-alert pg-alert--error" role="alert">
            {serverError}
          </div>
        )}

        {recommendation && (
          <section className="pg-alert pg-alert--success" aria-live="polite">
            <h2>Recommended package</h2>
            <p className="pg-package">{recommendation}</p>
          </section>
        )}
      </div>
      {footer}
    </div>
  )
}
