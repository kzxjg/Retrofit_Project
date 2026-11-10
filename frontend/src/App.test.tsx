import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { ADVANCED, DEFAULT_WEIGHTS, TEST_REPORT, TEST_SPEC, ZONE_A, ZONE_B } from './testSpec'

function reply(body: unknown, status = 200) {
  return { ok: status < 400, status, json: async () => body }
}

// A pretend server. The real one is not needed to test the page.
function mockServer(recommend: () => ReturnType<typeof reply> = () => reply(TEST_REPORT)) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    void init
    if (url === '/api/form-spec') return reply(TEST_SPEC)
    if (url === '/api/recommend') return recommend()
    throw new Error(`unexpected request to ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const type = (box: HTMLElement, value: string) => fireEvent.change(box, { target: { value } })
const postalBox = () => screen.findByLabelText('Postal code / location')
const yearBox = () => screen.getByLabelText('Approximate construction year')
const areaBox = () => screen.getByLabelText('Approximate floor area (m²)')
const zoneBox = () => screen.getByLabelText('Climate zone')
const button = (name: RegExp | string) => screen.getByRole('button', { name })
const step = (name: RegExp) => within(screen.getByRole('navigation', { name: 'Main sections' })).getByRole('button', { name })

async function fillHome() {
  type(await postalBox(), 'N9A 1A1')
  type(yearBox(), '1985')
  type(areaBox(), '180')
  type(screen.getByLabelText('Building form (if known)'), 'Detached house')
  type(zoneBox(), ZONE_B)
}

async function fillAll() {
  await fillHome()
  fireEvent.click(button(/continue to priorities/i))
  type(screen.getByLabelText('Available retrofit budget (CAD)'), '30000')
  type(screen.getByLabelText('What matters most to you?'), 'Balanced outcome')
}

async function apply() {
  fireEvent.click(button(/apply preferences/i))
  await screen.findByRole('heading', { name: /baseline energy performance/i })
}

function sentAnswers(fetchMock: ReturnType<typeof mockServer>) {
  const call = fetchMock.mock.calls.find(([url]) => url === '/api/recommend')
  expect(call).toBeDefined()
  return JSON.parse(String(call![1]!.body)).answers
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('loading the page', () => {
  it('starts on the home profile, with the five steps and the map', async () => {
    mockServer()
    const { container } = render(<App />)
    await postalBox()
    expect(screen.getByRole('heading', { name: '1. Tell us about your home' })).toBeInTheDocument()
    for (const name of ['Home profile', 'Your priorities', 'Energy assessment', 'Recommendations', 'Results & net zero']) {
      expect(step(new RegExp(name))).toBeInTheDocument()
    }
    expect(step(/home profile/i)).toHaveAttribute('aria-current', 'step')
    for (const f of TEST_SPEC.sections[0].fields) expect(screen.getByLabelText(f.label)).toBeInTheDocument()
    expect(container.querySelectorAll('[data-zone]').length).toBeGreaterThan(0)
  })

  it('names the tool in the header and shows the logo in the footer', async () => {
    mockServer()
    render(<App />)
    await postalBox()
    expect(screen.getByRole('banner')).toHaveTextContent('Home Retrofit Advisor')
    const logo = screen.getByRole('img', { name: 'University of Windsor' })
    expect(logo.closest('footer')).not.toBeNull()
  })

  it('says so when the server cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => reply({}, 500)))
    render(<App />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load the form/i)
    expect(screen.getByRole('banner')).toHaveTextContent('Home Retrofit Advisor')
  })
})

describe('step 1: home profile', () => {
  it('will not continue until the required questions are answered, and says which', async () => {
    mockServer()
    render(<App />)
    await postalBox()
    fireEvent.click(button(/continue to priorities/i))
    expect(screen.getByRole('heading', { name: '1. Tell us about your home' })).toBeInTheDocument()
    expect(await postalBox()).toHaveAccessibleDescription('Postal code / location is required.')
    expect(zoneBox()).toHaveAccessibleDescription('Climate zone is required.')
    expect(screen.getByLabelText('Building form (if known)')).toBeValid() // optional
    expect(document.activeElement).toBe(await postalBox())
  })

  it('continues to the priorities once it is complete', async () => {
    mockServer()
    render(<App />)
    await fillHome()
    fireEvent.click(button(/continue to priorities/i))
    expect(screen.getByRole('heading', { name: '2. Set your budget and priorities' })).toBeInTheDocument()
    expect(step(/your priorities/i)).toHaveAttribute('aria-current', 'step')
  })

  it('shows a postal code mistake at once', async () => {
    mockServer()
    render(<App />)
    type(await postalBox(), 'D')
    expect(await postalBox()).toHaveAccessibleDescription(/character 1 must be a letter/i)
  })

  it('waits until the user leaves the box before saying a floor area is too small', async () => {
    mockServer()
    render(<App />)
    await postalBox()
    type(areaBox(), '2')
    expect(areaBox()).toBeValid()
    fireEvent.blur(areaBox())
    expect(areaBox()).toHaveAccessibleDescription('Enter a value between 30 and 1000.')
  })

  it('offers only the climate zones that occur where the postal code is', async () => {
    mockServer()
    render(<App />)
    type(await postalBox(), 'N9A 1A1')
    const options = within(zoneBox()).getAllByRole('option').map((o) => o.getAttribute('value'))
    expect(options).toEqual(['', ZONE_B])
  })

  it('keeps a chosen zone listed, with its error, when the postal code changes so it no longer fits', async () => {
    mockServer()
    render(<App />)
    type(await postalBox(), 'V6B 1A1')
    type(zoneBox(), ZONE_A)
    expect(zoneBox()).toBeValid()
    type(await postalBox(), 'N9A 1A1')
    const options = within(zoneBox()).getAllByRole('option').map((o) => o.getAttribute('value'))
    expect(options).toEqual([ZONE_A, ZONE_B]) // the old choice stays, so it is still shown as chosen
    expect(zoneBox()).toHaveValue(ZONE_A)
    expect(zoneBox()).toHaveAccessibleDescription(/does not occur where your postal code is/i)
    fireEvent.click(button(/continue to priorities/i))
    expect(screen.getByRole('heading', { name: '1. Tell us about your home' })).toBeInTheDocument()
  })

  it('chooses the climate zone from the map', async () => {
    mockServer()
    const { container } = render(<App />)
    await postalBox()
    fireEvent.click(container.querySelector('[data-zone="zone4"]')!)
    expect(zoneBox()).toHaveValue(ZONE_A)
  })

  it('previews the matched archetype from the year and building form', async () => {
    mockServer()
    render(<App />)
    await fillHome()
    expect(screen.getByText('1980–1989 · Detached house')).toBeInTheDocument()
    expect(screen.getByText('180 m²')).toBeInTheDocument()
  })
})

describe('step 2: priorities', () => {
  it('asks what matters most in simple mode, and shows sliders in advanced mode', async () => {
    mockServer()
    render(<App />)
    await fillHome()
    fireEvent.click(button(/continue to priorities/i))
    expect(screen.getByLabelText('What matters most to you?')).toBeInTheDocument()
    expect(screen.queryByLabelText('Initial cost')).not.toBeInTheDocument()
    type(screen.getByLabelText('Preference setting'), ADVANCED)
    expect(screen.queryByLabelText('What matters most to you?')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Initial cost')).toHaveValue('20')
  })

  it('sends the answers as the server expects them, without hidden questions', async () => {
    const fetchMock = mockServer()
    render(<App />)
    await fillAll()
    await apply()
    expect(sentAnswers(fetchMock)).toEqual({
      postal_code: 'N9A 1A1',
      year_built: 1985,
      floor_area: 180,
      building_form: 'Detached house',
      zone: ZONE_B,
      budget: 30000,
      preference_mode: TEST_SPEC.sections[1].fields[1].options![0],
      priority: 'Balanced outcome',
    })
  })

  it('sends the slider weights in advanced mode', async () => {
    const fetchMock = mockServer()
    render(<App />)
    await fillAll()
    type(screen.getByLabelText('Preference setting'), ADVANCED)
    type(screen.getByLabelText('Payback'), '60')
    await apply()
    const sent = sentAnswers(fetchMock)
    expect(sent.weights).toEqual({ ...DEFAULT_WEIGHTS, payback: 60 })
    expect(sent).not.toHaveProperty('priority')
  })

  it('refuses weights that are all zero', async () => {
    const fetchMock = mockServer()
    render(<App />)
    await fillAll()
    type(screen.getByLabelText('Preference setting'), ADVANCED)
    for (const name of ['Initial cost', 'Energy savings', 'Payback']) type(screen.getByLabelText(name), '0')
    fireEvent.click(button(/apply preferences/i))
    expect(screen.getByText('Give at least one criterion a weight above 0.')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url]) => url === '/api/recommend')).toBe(false)
  })

  it('is locked in the side panel until the home profile is complete', async () => {
    mockServer()
    render(<App />)
    await postalBox()
    expect(step(/your priorities/i)).toBeDisabled()
    expect(step(/your priorities/i)).toHaveAttribute('title', 'Complete your home profile first.')
    fireEvent.click(step(/your priorities/i))
    expect(screen.getByRole('heading', { name: '1. Tell us about your home' })).toBeInTheDocument()
    expect(screen.getByText('Complete each step to unlock the next.')).toBeInTheDocument()

    await fillHome()
    expect(step(/your priorities/i)).toBeEnabled()
    fireEvent.click(step(/your priorities/i))
    expect(screen.getByRole('heading', { name: '2. Set your budget and priorities' })).toBeInTheDocument()
  })

  it('locks again when a required home answer is cleared', async () => {
    mockServer()
    render(<App />)
    await fillHome()
    expect(step(/your priorities/i)).toBeEnabled()
    type(areaBox(), '')
    expect(step(/your priorities/i)).toBeDisabled()
  })

  it('stays locked while the home profile has a mistake, even with every question answered', async () => {
    mockServer()
    render(<App />)
    await fillHome()
    type(areaBox(), '5') // below the 30 m² minimum
    expect(step(/your priorities/i)).toBeDisabled()
  })
})

describe('steps 3 to 5: the report', () => {
  it('are locked in the side panel until a report has been made', async () => {
    mockServer()
    render(<App />)
    const reportSteps = [/energy assessment/i, /recommendations/i, /results/i]
    await postalBox()
    for (const name of reportSteps) {
      expect(step(name)).toBeDisabled()
      expect(step(name)).toHaveAttribute('title', 'Complete your home profile first.')
    }
    await fillHome()
    for (const name of reportSteps) expect(step(name)).toHaveAttribute('title', 'Set your budget and priorities first.')
    fireEvent.click(button(/continue to priorities/i))
    type(screen.getByLabelText('Available retrofit budget (CAD)'), '30000')
    type(screen.getByLabelText('What matters most to you?'), 'Balanced outcome')
    for (const name of reportSteps) {
      expect(step(name)).toBeDisabled()
      expect(step(name)).toHaveAttribute('title', 'Apply your preferences to create the report first.')
    }
    await apply()
    for (const name of reportSteps) expect(step(name)).toBeEnabled()
    expect(screen.queryByText('Complete each step to unlock the next.')).not.toBeInTheDocument()
  })

  it('shows the baseline the server worked out', async () => {
    mockServer()
    render(<App />)
    await fillAll()
    await apply()
    expect(screen.getByText('28,800')).toBeInTheDocument()
    expect(screen.getByText('5.8')).toBeInTheDocument()
    expect(screen.getByText('Detached house, Generation 1 (1941 - 1996)')).toBeInTheDocument()
  })

  it('lists packages within the budget by default, and all of them on request', async () => {
    mockServer()
    render(<App />)
    await fillAll()
    await apply()
    fireEvent.click(button(/view retrofit options/i))
    const names = () => within(screen.getByRole('list', { name: 'Retrofit packages' })).getAllByRole('heading').map((h) => h.textContent)
    expect(names()).toEqual(['1. Heat pump package', '2. Air sealing package'])
    type(screen.getByLabelText('Budget filter'), 'all')
    expect(names()).toEqual(['1. Whole-home package', '2. Heat pump package', '3. Air sealing package'])
    type(screen.getByLabelText('Rank by'), 'cost')
    expect(names()).toEqual(['1. Air sealing package', '2. Heat pump package', '3. Whole-home package'])
    expect(screen.getByText('Over budget')).toBeInTheDocument()
  })

  it('says so when nothing fits the budget', async () => {
    mockServer(() => reply({ ...TEST_REPORT, packages: TEST_REPORT.packages.map((p) => ({ ...p, within_budget: false })) }))
    render(<App />)
    await fillAll()
    await apply()
    fireEvent.click(step(/recommendations/i))
    expect(screen.getByText(/no options fit the current budget/i)).toBeInTheDocument()
  })

  it('shows the cost summary of the package the user views', async () => {
    mockServer()
    render(<App />)
    await fillAll()
    await apply()
    fireEvent.click(step(/recommendations/i))
    const basic = within(screen.getByRole('list', { name: 'Retrofit packages' })).getAllByRole('listitem')[1]
    fireEvent.click(within(basic).getByRole('button', { name: 'View this package' }))
    expect(screen.getByRole('heading', { name: /results, climate resilience/i })).toBeInTheDocument()
    expect(screen.getByText('Air sealing package', { selector: 'strong' })).toBeInTheDocument()
    expect(screen.getByText('$11,500')).toBeInTheDocument()
    expect(screen.getByText('$10,350')).toBeInTheDocument()
  })

  it('warns when the answers change after the report was made, and can update it', async () => {
    const fetchMock = mockServer()
    render(<App />)
    await fillAll()
    await apply()
    expect(screen.queryByText(/your answers have changed/i)).not.toBeInTheDocument()
    fireEvent.click(step(/your priorities/i))
    type(screen.getByLabelText('Available retrofit budget (CAD)'), '50000')
    fireEvent.click(step(/energy assessment/i))
    expect(screen.getByText(/your answers have changed/i)).toBeInTheDocument()
    fireEvent.click(button('Update report'))
    await screen.findByRole('heading', { name: /baseline energy performance/i })
    expect(await screen.findByText('28,800')).toBeInTheDocument()
    expect(screen.queryByText(/your answers have changed/i)).not.toBeInTheDocument()
    expect(fetchMock.mock.calls.filter(([url]) => url === '/api/recommend')).toHaveLength(2)
  })
})

describe('problems from the server', () => {
  it("takes the user to the question the server refused, with the server's words", async () => {
    mockServer(() => reply({ errors: [{ field: 'zone', message: 'Zone 5 does not occur where postal code N9A 1A1 is.' }] }, 422))
    render(<App />)
    await fillAll()
    fireEvent.click(button(/apply preferences/i))
    expect(await screen.findByText('Zone 5 does not occur where postal code N9A 1A1 is.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '1. Tell us about your home' })).toBeInTheDocument()
  })

  it('passes on the wait message when there are too many requests', async () => {
    const message = 'Too many requests. Please wait a minute and try again.'
    mockServer(() => reply({ errors: [{ field: '', message }] }, 429))
    render(<App />)
    await fillAll()
    fireEvent.click(button(/apply preferences/i))
    expect(await screen.findByRole('alert')).toHaveTextContent(message)
  })

  it("shows the server's words in a banner when they are not about any one question", async () => {
    mockServer(() =>
      reply({ errors: [{ field: 'answers', message: 'Too many fields in the request.' }, { field: 'shoe_size', message: 'Unknown field.' }] }, 422),
    )
    render(<App />)
    await fillAll()
    fireEvent.click(button(/apply preferences/i))
    expect(await screen.findByRole('alert')).toHaveTextContent('Too many fields in the request. Unknown field.')
    expect(screen.getByRole('heading', { name: '2. Set your budget and priorities' })).toBeInTheDocument()
  })

  it("clears the server's complaint about a question once the user changes that answer", async () => {
    const message = 'Building form: choose one of the listed options.'
    mockServer(() => reply({ errors: [{ field: 'building_form', message }] }, 422))
    render(<App />)
    await fillAll()
    fireEvent.click(button(/apply preferences/i))
    const form = await screen.findByLabelText('Building form (if known)')
    expect(form).toHaveAccessibleDescription(message)
    expect(form).toBeInvalid()
    type(form, 'Townhouse')
    expect(form).not.toHaveAccessibleDescription(message)
    expect(form).toBeValid()
  })

  it('sends the answers only once, however often the button is pressed while waiting', async () => {
    let answer: (value: ReturnType<typeof reply>) => void = () => {}
    const pending = new Promise<ReturnType<typeof reply>>((resolve) => (answer = resolve))
    const fetchMock = vi.fn(async (url: string) => (url === '/api/form-spec' ? reply(TEST_SPEC) : pending))
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    await fillAll()
    fireEvent.click(button(/apply preferences/i))
    const waiting = await screen.findByRole('button', { name: 'Calculating…' })
    expect(waiting).toBeDisabled()
    fireEvent.click(waiting)
    fireEvent.click(waiting)
    expect(fetchMock.mock.calls.filter(([url]) => url === '/api/recommend')).toHaveLength(1)
    answer(reply(TEST_REPORT))
    await screen.findByRole('heading', { name: /baseline energy performance/i })
  })

  it('says the server could not be reached when the request fails', async () => {
    mockServer(() => reply({}, 500))
    render(<App />)
    await fillAll()
    fireEvent.click(button(/apply preferences/i))
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not get a recommendation/i)
  })
})
