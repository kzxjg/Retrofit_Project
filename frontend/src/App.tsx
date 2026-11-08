import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { ServerMessage, fetchSpec, submitAnswers } from './api'
import CanadaMap from './CanadaMap'
import FieldControl from './FieldControl'
import { allFields, arrangePackages, buildPayload, decadeLabel, fieldIssue, initialAnswers, isEmpty, isVisible, validate } from './formLogic'
import { BaselineStep, RecommendationsStep, ResultsStep } from './ReportSteps'
import { optionForZoneId, zoneIdFromOption } from './zones'
import type { Answer, Answers, ApiError, BudgetFilter, Field, Report, SortMode, Spec } from './types'
import './App.css'

type StepId = 'home' | 'preferences' | 'baseline' | 'recommendations' | 'results'

const STEPS: { id: StepId; label: string }[] = [
  { id: 'home', label: 'Home profile' },
  { id: 'preferences', label: 'Your priorities' },
  { id: 'baseline', label: 'Energy assessment' },
  { id: 'recommendations', label: 'Recommendations' },
  { id: 'results', label: 'Results & net zero' },
]

// The server's two sections of questions, and the step each is asked in.
const SECTION_STEP: Record<string, StepId> = { home: 'home', priorities: 'preferences' }

function scrollToTop() {
  try {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  } catch {
    // not available in every environment (e.g. tests)
  }
}

export default function App() {
  const [spec, setSpec] = useState<Spec | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [step, setStep] = useState<StepId>('home')
  const [answers, setAnswers] = useState<Answers>({})
  const [attempted, setAttempted] = useState<Record<string, boolean>>({}) // per section: tried to move on
  const [touched, setTouched] = useState<Record<string, boolean>>({})
  const focusField = useRef<string | null>(null) // a problem to take the user to after the next render
  const [serverErrors, setServerErrors] = useState<ApiError[]>([])
  const [serverError, setServerError] = useState<string | null>(null)
  const [report, setReport] = useState<Report | null>(null)
  const [reportFor, setReportFor] = useState<string>('') // the answers the report was made from
  const [submitting, setSubmitting] = useState(false)
  const [sort, setSort] = useState<SortMode>('personal')
  const [filter, setFilter] = useState<BudgetFilter>('within')
  const [chosenId, setChosenId] = useState<string | null>(null)

  useEffect(() => {
    fetchSpec()
      .then((s) => {
        setSpec(s)
        setAnswers(initialAnswers(s))
      })
      .catch((err: unknown) => setLoadError(err instanceof Error ? err.message : 'Could not reach the backend.'))
  }, [])

  // after moving to a step to show a problem, put the cursor on it
  useEffect(() => {
    if (!focusField.current) return
    document.getElementById(`f-${focusField.current}`)?.focus()
    focusField.current = null
  })

  function go(id: StepId) {
    setStep(id)
    scrollToTop()
  }

  function leaveField(id: string) {
    setTouched((prev) => (prev[id] ? prev : { ...prev, [id]: true }))
  }

  function changeField(id: string, value: Answer) {
    setServerErrors((prev) => (prev.some((e) => e.field === id) ? prev.filter((e) => e.field !== id) : prev))
    setAnswers((prev) => ({ ...prev, [id]: value }))
  }

  function chooseOnMap(zoneId: string) {
    const options = spec ? allFields(spec).find((f) => f.id === 'zone')?.options : undefined
    const option = options ? optionForZoneId(options, zoneId) : undefined
    if (option) changeField('zone', option)
  }

  const header = (
    <header className="pg-top">
      <div className="pg-top-inner">
        <div className="pg-brand">
          Home Retrofit Advisor
          <small>Decision support for more efficient, lower-carbon homes</small>
        </div>
        <div className="pg-status">● Estimates use sample data</div>
      </div>
    </header>
  )

  const footer = (
    <footer className="pg-footer">
      <p className="pg-smalltext">
        Replace sample calculations with validated archetype, EnergyPlus, cost and carbon datasets before real-world use.
      </p>
      <img className="pg-logo" src="/uwindsor-logo.png" alt="University of Windsor" width={151} height={56} />
    </footer>
  )

  if (!spec) {
    return (
      <div className="pg">
        {header}
        <main className="pg-main">
          {loadError ? (
            <div className="pg-alert pg-alert--error" role="alert">
              Could not load the form: {loadError}. Is the Django server running?
            </div>
          ) : (
            <p className="pg-help">Loading the form…</p>
          )}
        </main>
        {footer}
      </div>
    )
  }

  const sectionFields = (sectionId: string) => spec.sections.find((s) => s.id === sectionId)?.fields ?? []
  const stepOf = (fieldId: string): StepId => {
    const section = spec.sections.find((s) => s.fields.some((f) => f.id === fieldId))
    return (section && SECTION_STEP[section.id]) ?? 'home'
  }
  const sectionOf = (f: Field) => spec.sections.find((s) => s.fields.includes(f))?.id ?? ''

  const errorFor = (f: Field): string | null => {
    if (!isVisible(f, answers)) return null
    const value = answers[f.id]
    if (attempted[sectionOf(f)] && f.required && isEmpty(value)) return `${f.label} is required.`
    const issue = fieldIssue(f, value, answers)
    if (issue && (issue.early || touched[f.id] || attempted[sectionOf(f)])) return issue.message
    return serverErrors.find((e) => e.field === f.id)?.message ?? null
  }
  const control = (f: Field) => (
    <FieldControl key={f.id} field={f} answers={answers} onChange={changeField} error={errorFor(f)} onBlur={() => leaveField(f.id)} />
  )

  /** Try to leave a section of questions: true when it is ready, otherwise show what needs fixing. */
  function checkSection(sectionId: string): boolean {
    setAttempted((prev) => ({ ...prev, [sectionId]: true }))
    const problems = validate(spec!, answers, sectionFields(sectionId))
    if (problems.length === 0) return true
    go(SECTION_STEP[sectionId] ?? 'home')
    focusField.current = problems[0].field
    return false
  }

  const payloadKey = JSON.stringify(buildPayload(spec, answers))
  const stale = report !== null && reportFor !== payloadKey

  async function makeReport() {
    if (!spec) return
    setServerError(null)
    setServerErrors([])
    setAttempted(Object.fromEntries(spec.sections.map((s) => [s.id, true])))
    const problems = validate(spec, answers)
    if (problems.length > 0) {
      go(stepOf(problems[0].field)) // take the user to the first problem
      focusField.current = problems[0].field
      return
    }

    setSubmitting(true)
    try {
      const outcome = await submitAnswers(buildPayload(spec, answers))
      if (outcome.ok) {
        setReport(outcome.report)
        setReportFor(payloadKey)
        setChosenId(null)
        go('baseline')
      } else {
        setServerErrors(outcome.errors)
        const first = outcome.errors.find((e) => allFields(spec).some((f) => f.id === e.field))
        if (first) {
          go(stepOf(first.field))
          focusField.current = first.field
        } else {
          setServerError(outcome.errors.map((e) => e.message).join(' '))
        }
      }
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

  const homeFields = sectionFields('home').filter((f) => !f.placement)
  const mapFields = sectionFields('home').filter((f) => f.placement === 'map')
  const selectedZoneId = typeof answers.zone === 'string' ? zoneIdFromOption(answers.zone) : null
  const decade = decadeLabel(answers.year_built)
  const form = typeof answers.building_form === 'string' && answers.building_form ? answers.building_form : null
  const area = typeof answers.floor_area === 'string' && answers.floor_area.trim() ? answers.floor_area.trim() : null

  const reportButton = (label: string) => (
    <button type="button" className="pg-btn" onClick={makeReport} disabled={submitting}>
      {submitting ? 'Calculating…' : label}
    </button>
  )

  /** Steps 3 to 5 need a report; until there is one, say how to get it. */
  const needsReport = (content: (r: Report) => ReactNode) => {
    if (!report) {
      return (
        <div className="pg-callout">
          <strong>No report yet</strong>
          <p className="pg-smalltext">Fill in your home profile and priorities, then apply them to see this step.</p>
          <div className="pg-actions">
            <button type="button" className="pg-btn pg-btn--secondary" onClick={() => go('home')}>
              ← Home profile
            </button>
            {reportButton('Create my report →')}
          </div>
        </div>
      )
    }
    return (
      <>
        {stale && (
          <div className="pg-callout pg-callout--warn" role="status">
            <strong>Your answers have changed since this report was made.</strong>
            <div className="pg-actions pg-actions--tight">{reportButton('Update report')}</div>
          </div>
        )}
        {content(report)}
      </>
    )
  }

  const chosen = report
    ? (report.packages.find((p) => p.id === chosenId) ?? arrangePackages(report.packages, sort, filter)[0] ?? report.packages[0])
    : null

  const sections: Record<StepId, ReactNode> = {
    home: (
      <>
        <section className="pg-box" aria-labelledby="h-home">
          <h2 id="h-home">1. Tell us about your home</h2>
          <p className="pg-muted">
            Only a few basic details are needed. The tool will use them to identify a suitable building archetype.
          </p>
          <div className="pg-grid2">{homeFields.map(control)}</div>
          <div className="pg-map-block">
            <CanadaMap selectedZoneId={selectedZoneId} onSelectZone={chooseOnMap}>
              {mapFields.map(control)}
            </CanadaMap>
          </div>
          <div className="pg-callout">
            <strong>How archetype matching works</strong>
            <div className="pg-smalltext">
              Location, climate zone, construction period, floor area and building form are used to select a
              representative existing model. Detailed wall, window and insulation information is not required for this
              first assessment.
            </div>
          </div>
          <div className="pg-actions">
            <span className="pg-smalltext">You can edit these details at any time.</span>
            <button type="button" className="pg-btn" onClick={() => checkSection('home') && go('preferences')}>
              Continue to priorities →
            </button>
          </div>
        </section>
        <section className="pg-box" aria-labelledby="h-archetype">
          <h3 id="h-archetype">Matched building archetype</h3>
          <div className="pg-grid2">
            <div>
              <span className="pg-tag pg-tag--accent">Illustrative match</span>
              <p className="pg-archetype">
                {decade ?? 'Construction period'} · {form ?? 'Building form not given'}
              </p>
              <p className="pg-smalltext">
                Representative archetype selected from location, construction period and building form. Actual match
                depends on the project archetype library.
              </p>
            </div>
            <div className="pg-metric">
              <div className="pg-metric-k">Assessment floor area</div>
              <div className="pg-metric-v">{area ? `${area} m²` : '—'}</div>
              <div className="pg-metric-d">Based on your input</div>
            </div>
          </div>
        </section>
      </>
    ),

    preferences: (
      <section className="pg-box" aria-labelledby="h-preferences">
        <h2 id="h-preferences">2. Set your budget and priorities</h2>
        <div className="pg-grid2">{sectionFields('priorities').filter((f) => f.type !== 'weights' && isVisible(f, answers)).map(control)}</div>
        {sectionFields('priorities').filter((f) => f.type === 'weights' && isVisible(f, answers)).map(control)}
        <div className="pg-actions">
          <button type="button" className="pg-btn pg-btn--secondary" onClick={() => go('home')}>
            ← Back
          </button>
          {reportButton('Apply preferences →')}
        </div>
      </section>
    ),

    baseline: (
      <section className="pg-box" aria-labelledby="h-baseline">
        <h2 id="h-baseline">3. Baseline energy performance</h2>
        <p className="pg-muted">
          Illustrative baseline estimates are shown here. In a deployed tool, these values are populated by the calibrated
          archetype and EnergyPlus simulation.
        </p>
        {needsReport((r) => (
          <>
            <BaselineStep report={r} />
            <div className="pg-actions">
              <button type="button" className="pg-btn pg-btn--secondary" onClick={() => go('preferences')}>
                ← Back
              </button>
              <button type="button" className="pg-btn" onClick={() => go('recommendations')}>
                View retrofit options →
              </button>
            </div>
          </>
        ))}
      </section>
    ),

    recommendations: (
      <section className="pg-box" aria-labelledby="h-recommendations">
        <h2 id="h-recommendations">4. Ranked retrofit recommendations</h2>
        <p className="pg-muted">Options are ranked using your selected priorities and budget.</p>
        {needsReport((r) => (
          <RecommendationsStep
            report={r}
            sort={sort}
            filter={filter}
            onSort={setSort}
            onFilter={setFilter}
            onView={(id) => {
              setChosenId(id)
              go('results')
            }}
          />
        ))}
      </section>
    ),

    results: (
      <section className="pg-box" aria-labelledby="h-results">
        <h2 id="h-results">5. Results, climate resilience and net-zero progress</h2>
        {needsReport((r) => (
          <>
            <ResultsStep report={r} chosen={chosen!} />
            <div className="pg-actions">
              <button type="button" className="pg-btn pg-btn--secondary" onClick={() => go('recommendations')}>
                ← Back to options
              </button>
              <button type="button" className="pg-btn" onClick={() => window.print()}>
                Print / Save report
              </button>
            </div>
          </>
        ))}
      </section>
    ),
  }

  return (
    <div className="pg">
      {header}
      <main className="pg-main">
        <h1>Your Home Energy Report</h1>
        <p className="pg-sub">
          Explore retrofit options, compare costs and savings, and see how recommendations may perform in future climates.
        </p>
        <div className="pg-layout">
          <nav className="pg-nav" aria-label="Main sections">
            {STEPS.map((s, i) => (
              <button
                key={s.id}
                type="button"
                className={s.id === step ? 'pg-nav-btn pg-nav-btn--on' : 'pg-nav-btn'}
                aria-current={s.id === step ? 'step' : undefined}
                onClick={() => go(s.id)}
              >
                <span className="pg-step-num">{i + 1}</span>
                {s.label}
              </button>
            ))}
          </nav>
          <div className="pg-content">
            {serverError && (
              <div className="pg-alert pg-alert--error" role="alert">
                {serverError}
              </div>
            )}
            {sections[step]}
          </div>
        </div>
      </main>
      {footer}
    </div>
  )
}
