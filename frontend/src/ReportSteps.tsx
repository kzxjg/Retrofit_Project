// Steps 3 to 5: what the server worked out from the answers. Sorting and the budget filter only
// change how the packages are shown, so they stay on the page and are not sent to the server.
import { arrangePackages, money } from './formLogic'
import type { BudgetFilter, Package, Report, SortMode } from './types'

const SORT_OPTIONS: [SortMode, string][] = [
  ['personal', 'My priorities'],
  ['cost', 'Lowest initial cost'],
  ['savings', 'Highest energy savings'],
  ['carbon', 'Highest carbon reduction'],
  ['payback', 'Shortest payback'],
]

const kwh = (n: number) => Math.round(n).toLocaleString('en-CA')

function Metric({ k, v, d, small }: { k: string; v: string; d?: string; small?: boolean }) {
  return (
    <div className="pg-metric">
      <div className="pg-metric-k">{k}</div>
      <div className={small ? 'pg-metric-v pg-metric-v--small' : 'pg-metric-v'}>{v}</div>
      {d && <div className="pg-metric-d">{d}</div>}
    </div>
  )
}

export function BaselineStep({ report }: { report: Report }) {
  const b = report.baseline
  return (
    <>
      <div className="pg-grid3">
        <Metric k="Annual energy use" v={kwh(b.energy_kwh)} d="kWh/year" />
        <Metric k="Heating demand" v={kwh(b.heating_kwh)} d="kWh/year" />
        <Metric k="Cooling demand" v={kwh(b.cooling_kwh)} d="kWh/year" />
      </div>
      <div className="pg-grid2 pg-gap-top">
        <Metric k="Operational emissions" v={b.carbon_t.toFixed(1)} d="tonnes CO₂e/year" />
        <Metric
          k="Matched archetype"
          v={`${report.archetype.building_form}, ${report.archetype.period}`}
          d={`Representative model · ${Math.round(report.archetype.confidence * 100)}% match`}
          small
        />
      </div>
      <div className="pg-callout">
        <strong>Simulation pathway</strong>
        <div className="pg-smalltext">
          Archetype selection → baseline EnergyPlus model → individual retrofit simulations → combined retrofit
          simulations → cost, carbon and lifecycle assessment.
        </div>
      </div>
    </>
  )
}

type RecommendationsProps = {
  report: Report
  sort: SortMode
  filter: BudgetFilter
  onSort: (sort: SortMode) => void
  onFilter: (filter: BudgetFilter) => void
  onView: (id: string) => void
}

export function RecommendationsStep({ report, sort, filter, onSort, onFilter, onView }: RecommendationsProps) {
  const shown = arrangePackages(report.packages, sort, filter)
  return (
    <>
      <div className="pg-grid2">
        <div className="pg-field">
          <label htmlFor="sort-mode" className="pg-field-title">
            Rank by
          </label>
          <select id="sort-mode" className="pg-select" value={sort} onChange={(e) => onSort(e.target.value as SortMode)}>
            {SORT_OPTIONS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="pg-field">
          <label htmlFor="budget-filter" className="pg-field-title">
            Budget filter
          </label>
          <select id="budget-filter" className="pg-select" value={filter} onChange={(e) => onFilter(e.target.value as BudgetFilter)}>
            <option value="within">Show options within my budget</option>
            <option value="all">Show all options</option>
          </select>
        </div>
      </div>

      {shown.length === 0 ? (
        <div className="pg-callout">
          No options fit the current budget of {money(report.budget)}. Increase the budget or choose “Show all options”.
        </div>
      ) : (
        <ol className="pg-packages" aria-label="Retrofit packages">
          {shown.map((p, i) => (
            <li key={p.id} className={i === 0 ? 'pg-package pg-package--best' : 'pg-package'}>
              <div className="pg-package-head">
                <div>
                  <span className="pg-tag">{p.tag}</span>
                  <h3>
                    {i + 1}. {p.name}
                  </h3>
                </div>
                <div className="pg-package-tags">
                  {i === 0 && <span className="pg-tag pg-tag--accent">Top match</span>}
                  {!p.within_budget && <span className="pg-tag pg-tag--gold">Over budget</span>}
                </div>
              </div>
              <p className="pg-package-desc">{p.description}</p>
              <div className="pg-grid3">
                <Metric k="Initial cost" v={money(p.cost)} />
                <Metric k="Energy savings" v={`${p.saving_pct}%`} />
                <Metric k="Payback" v={`${p.payback_yrs} yrs`} />
              </div>
              <div className="pg-grid3">
                <Metric k="Operational carbon avoided" v={`${p.carbon_t.toFixed(1)} t/yr`} />
                <Metric k="Embodied carbon" v={`${p.embodied_t.toFixed(1)} t`} />
                <Metric k="Climate resilience" v={`${p.resilience}/100`} />
              </div>
              <button type="button" className="pg-btn pg-btn--small" onClick={() => onView(p.id)}>
                View this package
              </button>
            </li>
          ))}
        </ol>
      )}
      <p className="pg-smalltext">
        Combined packages account for interactions in principle; final results must be based on dedicated combined
        EnergyPlus simulations rather than adding individual savings. Sample estimates are for interface demonstration only.
      </p>
    </>
  )
}

export function ResultsStep({ report, chosen }: { report: Report; chosen: Package }) {
  return (
    <>
      <h3>Compare energy savings</h3>
      {report.packages.map((p) => (
        <div key={p.id} className="pg-barrow">
          <span>{p.name}</span>
          <div className="pg-track" role="img" aria-label={`${p.name}: ${p.saving_pct}% energy savings`}>
            <div className="pg-fill" style={{ width: `${Math.min(100, p.saving_pct)}%` }} />
          </div>
          <strong>{p.saving_pct}%</strong>
        </div>
      ))}

      <h3 className="pg-gap-top-lg">Future climate scenario assessment</h3>
      <p className="pg-smalltext">
        Illustrative 2040 scenario comparison. The deployed model should use selected regional climate files and run
        each retrofit package separately under each scenario.
      </p>
      <div className="pg-table-wrap">
        <table className="pg-table">
          <thead>
            <tr>
              <th>Climate scenario</th>
              <th>Heating demand</th>
              <th>Cooling demand</th>
              <th>Suggested approach</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Current climate</td>
              <td>Baseline</td>
              <td>Baseline</td>
              <td>Optimize current performance</td>
            </tr>
            <tr>
              <td>2040 – Moderate warming</td>
              <td>Lower</td>
              <td>Higher</td>
              <td>Balanced envelope and cooling</td>
            </tr>
            <tr>
              <td>2040 – High warming</td>
              <td>Lower</td>
              <td>Much higher</td>
              <td>Prioritize shading, cooling efficiency and resilience</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div className="pg-callout">
        <strong>Robust / low-regret recommendation</strong>
        <p className="pg-smalltext">
          Select the package that performs consistently well across multiple plausible future climates, rather than
          optimizing for one scenario alone.
        </p>
      </div>

      <h3 className="pg-gap-top-lg">Cost and carbon summary</h3>
      <p className="pg-smalltext">
        For: <strong>{chosen.name}</strong>
      </p>
      <div className="pg-grid3">
        <Metric k="Estimated project cost" v={money(chosen.cost)} d="Before incentives" />
        <Metric k="Potential incentives" v={money(chosen.incentive)} d="Eligibility to be verified" />
        <Metric k="Net investment" v={money(chosen.net_cost)} d="After illustrative incentives" />
      </div>
      <div className="pg-grid2 pg-gap-top">
        <Metric k="Operational carbon avoided" v={chosen.carbon_t.toFixed(1)} d="tonnes CO₂e/year" />
        <Metric k="Embodied carbon" v={chosen.embodied_t.toFixed(1)} d="tonnes CO₂e, estimated upfront" />
      </div>

      <h3 className="pg-gap-top-lg">Progress towards your net-zero target</h3>
      <div className="pg-barrow">
        <span>Operational emissions</span>
        <div className="pg-track" role="img" aria-label={`${chosen.saving_pct}% of operational emissions`}>
          <div className="pg-fill" style={{ width: `${Math.min(100, chosen.saving_pct)}%` }} />
        </div>
        <strong>{chosen.saving_pct}%</strong>
      </div>
      <p className="pg-smalltext">
        This is an indicative reduction in operational emissions, not a declaration of net zero. The project must define
        the target year, emissions boundary, energy sources and treatment of embodied/lifecycle carbon.
      </p>

      <h3 className="pg-gap-top-lg">Incentives and equipment timing</h3>
      <p className="pg-smalltext">
        Show current government programs, eligibility, application dates and estimated rebate values after verification
        against official sources. Existing heating/cooling equipment age and remaining service life can be added as
        optional inputs in a later phase.
      </p>
    </>
  )
}
