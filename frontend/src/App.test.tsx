import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { AREA, AREA_BANDS, AREA_BANDS_FT, IMPERIAL, METRIC, RENOVATION_ELEMENTS, TEST_PROGRAMS, TEST_SPEC, TYPED_YEAR, TYPED_YEAR_LABEL, ZONE_A, ZONE_B } from './testSpec'

function reply(body: unknown, status = 200) {
  return { ok: status < 400, status, json: async () => body }
}

// A pretend server. The real one is not needed to test the page.
function mockServer(recommend: () => ReturnType<typeof reply> = () => reply({ package: 'Equipment Electrification' })) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    void init
    if (url === '/api/form-spec') return reply(TEST_SPEC)
    if (url.startsWith('/api/incentives')) return reply({ programs: TEST_PROGRAMS })
    if (url === '/api/recommend') return recommend()
    throw new Error(`unexpected request to ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const escapeRe = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const postalBox = () => screen.findByLabelText(/postal code/i)
const zoneBox = () => screen.getByLabelText('Climate zone')
const yearBox = () => screen.getByLabelText('Year built')
const radio = (group: string, option: string) =>
  within(screen.getByRole('group', { name: group })).getByRole('radio', { name: option })

async function fillValid() {
  fireEvent.change(await postalBox(), { target: { value: 'N9A 1A1' } })
  fireEvent.change(zoneBox(), { target: { value: ZONE_A } })
  fireEvent.change(yearBox(), { target: { value: TYPED_YEAR } })
  fireEvent.click(radio('Preferred units', METRIC))
  fireEvent.change(screen.getByLabelText(/total floor area/i), { target: { value: AREA.A } })
  fireEvent.change(screen.getByLabelText('Number of storeys'), { target: { value: '2' } })
  fireEvent.change(screen.getByLabelText(/type of house/i), { target: { value: 'Detached house' } })
  fireEvent.click(screen.getByRole('checkbox', { name: 'Reduce energy bills' }))
}

function submit() {
  fireEvent.click(screen.getByRole('button', { name: /get my recommendation/i }))
}

function sentAnswers(fetchMock: ReturnType<typeof mockServer>) {
  const call = fetchMock.mock.calls.find(([url]) => url === '/api/recommend')
  expect(call).toBeDefined()
  return JSON.parse(String(call![1]!.body)).answers
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('loading the form', () => {
  it('draws every question and section from the server', async () => {
    mockServer()
    render(<App />)
    await postalBox()
    for (const section of TEST_SPEC.sections) {
      expect(screen.getByRole('heading', { name: section.title })).toBeInTheDocument()
      for (const field of section.fields.filter((f) => !f.show_if)) {
        expect(screen.getAllByText(new RegExp(escapeRe(field.label))).length).toBeGreaterThan(0)
      }
    }
    expect(screen.getByRole('heading', { name: 'Data review and validation' })).toBeInTheDocument()
  })

  it('says so when the server cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => reply({}, 500)))
    render(<App />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load the form/i)
  })
})

describe('header', () => {
  it('names the tool in a header bar', async () => {
    mockServer()
    render(<App />)
    await postalBox()
    expect(screen.getByRole('banner')).toHaveTextContent('Retrofit Decision Tool')
  })

  it('is there while the form loads and when it cannot be loaded', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => reply({}, 500)))
    render(<App />)
    expect(screen.getByRole('banner')).toHaveTextContent('Retrofit Decision Tool')
    await screen.findByRole('alert')
    expect(screen.getByRole('banner')).toHaveTextContent('Retrofit Decision Tool')
  })
})

describe('logo', () => {
  it('shows the University of Windsor logo in the footer, at the bottom of the page', async () => {
    mockServer()
    const { container } = render(<App />)
    await postalBox()
    const logo = screen.getByRole('img', { name: 'University of Windsor' })
    expect(logo.closest('footer')).not.toBeNull()
    expect(logo).toHaveAttribute('src', '/uwindsor-logo.png')
    const questions = screen.getByLabelText(/typical monthly energy bill/i)
    expect(questions.compareDocumentPosition(container.querySelector('footer')!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('is also shown while the form loads and when it cannot be loaded', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => reply({}, 500)))
    render(<App />)
    expect(screen.getByRole('img', { name: 'University of Windsor' })).toBeInTheDocument()
    await screen.findByRole('alert')
    expect(screen.getByRole('img', { name: 'University of Windsor' })).toBeInTheDocument()
  })
})

describe('problems are shown while the user types', () => {
  const temperature = () => screen.getByLabelText(/preferred indoor temperature/i)
  const type = (box: HTMLElement, value: string) => fireEvent.change(box, { target: { value } })

  it('shows a value that is too high under its own question at once, with no alert at the bottom', async () => {
    mockServer()
    render(<App />)
    await postalBox()
    type(temperature(), '45')
    expect(temperature()).toHaveAccessibleDescription('Enter a value between 10 and 30 °C.')
    expect(temperature()).toBeInvalid()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    type(temperature(), '20')
    expect(temperature()).toBeValid()
    expect(screen.queryByText(/enter a value between/i)).not.toBeInTheDocument()
  })

  it('waits until the user leaves the box before saying a value is too small', async () => {
    mockServer()
    render(<App />)
    await postalBox()
    type(temperature(), '5')
    expect(screen.queryByText(/enter a value between/i)).not.toBeInTheDocument() // there may be more digits coming
    fireEvent.blur(temperature())
    expect(screen.getByText('Enter a value between 10 and 30 °C.')).toBeInTheDocument()
  })

  it('speaks the units the user chose', async () => {
    mockServer()
    render(<App />)
    await postalBox()
    fireEvent.click(radio('Preferred units', IMPERIAL))
    type(temperature(), '95')
    expect(screen.getByText('Enter a value between 50 and 86 °F.')).toBeInTheDocument()
    type(temperature(), '68') // 20 °C
    expect(screen.queryByText(/enter a value between/i)).not.toBeInTheDocument()
    // the limits follow the units when they are switched
    type(temperature(), '40')
    fireEvent.click(radio('Preferred units', METRIC))
    expect(screen.getByText('Enter a value between 10 and 30 °C.')).toBeInTheDocument()
  })

  it('does not let letters or symbols be typed into a number box', async () => {
    mockServer()
    render(<App />)
    await postalBox()
    const bill = screen.getByLabelText(/typical monthly energy bill in winter/i)
    type(bill, 'abc12')
    expect(bill).toHaveValue('12')
    type(bill, '$1,500')
    expect(bill).toHaveValue('1500')
  })

  it('says so when a whole number is wanted, instead of changing what was typed', async () => {
    mockServer()
    render(<App />)
    await postalBox()
    type(yearBox(), '1985.5')
    expect(yearBox()).toHaveValue('1985.5')
    expect(screen.getByText('Enter a whole number.')).toBeInTheDocument()
  })

  it('checks the wall thickness in the units the user chose', async () => {
    mockServer()
    render(<App />)
    await postalBox()
    const wall = () => screen.getByLabelText(/exterior wall thickness/i)
    type(wall(), '5000')
    expect(screen.getByText('Enter a value between 20 and 1500 mm.')).toBeInTheDocument()
    fireEvent.click(radio('Preferred units', IMPERIAL))
    expect(screen.getByText('Enter a value between 0.8 and 59 in.')).toBeInTheDocument()
    type(wall(), '8')
    expect(screen.queryByText(/enter a value between/i)).not.toBeInTheDocument()
  })

  it('checks the year built against its limits', async () => {
    mockServer()
    render(<App />)
    await postalBox()
    type(yearBox(), '3000')
    expect(screen.getByText('Enter a whole number between 1800 and 2026.')).toBeInTheDocument()
    expect(screen.queryByText(/^Generation|^Pre 1941/)).not.toBeInTheDocument() // no generation for an impossible year
    type(yearBox(), '1985')
    expect(screen.queryByText(/enter a whole number between/i)).not.toBeInTheDocument()
  })

  it('tidies the postal code as it is typed and points at a wrong character at once', async () => {
    mockServer()
    render(<App />)
    const postal = await postalBox()
    type(postal, 'n9a1a1')
    expect(postal).toHaveValue('N9A 1A1')
    expect(postal).toBeValid()
    type(postal, '6')
    expect(screen.getByText(/character 1 must be a letter/i)).toBeInTheDocument()
    type(postal, 'N9')
    expect(screen.queryByText(/enter all 6 characters/i)).not.toBeInTheDocument() // unfinished is not wrong yet
    fireEvent.blur(postal)
    expect(screen.getByText('Enter all 6 characters, e.g. N9A 1A1.')).toBeInTheDocument()
  })

  it('keeps storeys above ground within the total number of storeys', async () => {
    mockServer()
    render(<App />)
    await postalBox()
    const storeys = screen.getByLabelText('Number of storeys')
    const above = screen.getByLabelText('Number of storeys above ground')
    type(storeys, '2')
    type(above, '3')
    fireEvent.blur(above)
    const rule = 'Storeys above ground cannot be more than the total number of storeys.'
    expect(screen.getByText(rule)).toBeInTheDocument()
    type(storeys, '4') // changing the other answer fixes it
    expect(screen.queryByText(rule)).not.toBeInTheDocument()
  })

  it('asks for a half-filled renovation record to be completed', async () => {
    mockServer()
    render(<App />)
    await postalBox()
    fireEvent.click(screen.getByRole('button', { name: 'Add renovation' }))
    const kind = screen.getByLabelText('Renovation 1 building element')
    type(kind, 'Roof')
    expect(screen.queryByText(/enter both a type and a year/i)).not.toBeInTheDocument()
    fireEvent.blur(kind)
    expect(screen.getByText('Renovation 1: enter both a type and a year, or remove it.')).toBeInTheDocument()
  })

  it('does not complain that required questions are empty until the user tries to submit', async () => {
    mockServer()
    render(<App />)
    await postalBox()
    expect(screen.queryByText('Year built is required.')).not.toBeInTheDocument()
    submit()
    expect(screen.getAllByText('Year built is required.')).toHaveLength(2) // under the question, and in the list
  })

  it('moves the cursor to the first problem when an incomplete form is submitted', async () => {
    mockServer()
    render(<App />)
    const postal = await postalBox()
    submit()
    expect(postal).toHaveFocus()
  })

  it('shows an answer the server refused under its question, and clears it when the answer is changed', async () => {
    const message = 'Preferred indoor temperature is outside the allowed range (10 to 30 °C).'
    mockServer(() => reply({ errors: [{ field: 'indoor_temperature', message }] }, 422))
    render(<App />)
    await fillValid()
    submit()
    await screen.findAllByText(message)
    expect(temperature()).toHaveAccessibleDescription(message)
    type(temperature(), '20')
    expect(screen.queryByText(message)).not.toBeInTheDocument()
  })
})

describe('top of the page', () => {
  it('asks for the typed answers first, then the map with the zone under it, then the other questions', async () => {
    mockServer()
    const { container } = render(<App />)
    const postal = await postalBox()
    const map = container.querySelector('svg')!
    const laterQuestion = screen.getByLabelText(/typical monthly energy bill/i)
    const before = (a: Element, b: Element) => a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING
    expect(before(postal, yearBox())).toBeTruthy()
    expect(before(yearBox(), map)).toBeTruthy()
    expect(before(map, zoneBox())).toBeTruthy()
    expect(before(zoneBox(), laterQuestion)).toBeTruthy()
  })

  it('puts the typed answers on the left and the map with the climate zone under it on the right', async () => {
    mockServer()
    const { container } = render(<App />)
    const postal = await postalBox()
    const start = container.querySelector('.pg-start')!
    const [left, right] = Array.from(start.children)
    for (const field of [postal, yearBox(), screen.getByLabelText(/total floor area/i)]) {
      expect(left).toContainElement(field as HTMLElement)
    }
    expect(left.querySelector('svg')).toBeNull()
    expect(right.querySelector('svg')).not.toBeNull()
    expect(right).toContainElement(zoneBox())
    expect(left).not.toContainElement(zoneBox())
    // the questions further down are not in the top row
    expect(start).not.toContainElement(screen.getByLabelText(/typical monthly energy bill/i))
  })

  it('takes the year built as typed text and shows which generation it is', async () => {
    mockServer()
    render(<App />)
    await postalBox()
    expect(yearBox()).toHaveAttribute('type', 'text')
    expect(screen.queryByText(/^Generation|^Pre 1941/)).not.toBeInTheDocument()
    fireEvent.change(yearBox(), { target: { value: TYPED_YEAR } })
    expect(screen.getByText(TYPED_YEAR_LABEL, { selector: 'p' })).toBeInTheDocument()
    fireEvent.change(yearBox(), { target: { value: '1930' } })
    expect(screen.getByText('Pre 1941')).toBeInTheDocument()
    fireEvent.change(yearBox(), { target: { value: 'abc' } })
    expect(screen.queryByText(/^Generation|^Pre 1941/)).not.toBeInTheDocument()
  })

  it('does not ask for the year built a second time further down', async () => {
    mockServer()
    render(<App />)
    await postalBox()
    expect(screen.getAllByLabelText('Year built')).toHaveLength(1)
  })

  it('shows a long answer in full as text, because the closed dropdown cuts it off', async () => {
    mockServer()
    render(<App />)
    await postalBox()
    expect(screen.queryByText(ZONE_A, { selector: 'p' })).not.toBeInTheDocument()
    fireEvent.change(zoneBox(), { target: { value: ZONE_A } })
    expect(screen.getByText(ZONE_A, { selector: 'p' })).toBeInTheDocument()
  })

  it('offers every zone from the server', async () => {
    mockServer()
    render(<App />)
    await postalBox()
    const options = within(zoneBox()).getAllByRole('option').map((o) => o.textContent)
    expect(options).toEqual(expect.arrayContaining([ZONE_A, ZONE_B]))
  })
})

describe('map', () => {
  const highlighted = (container: HTMLElement) =>
    Array.from(container.querySelectorAll('.cm-zone--on')).map((el) => el.getAttribute('data-zone'))

  it('highlights nothing until a zone is chosen', async () => {
    mockServer()
    const { container } = render(<App />)
    await postalBox()
    expect(highlighted(container)).toEqual([])
  })

  it('highlights the area of the zone that is chosen, and only that one', async () => {
    mockServer()
    const { container } = render(<App />)
    await postalBox()
    fireEvent.change(zoneBox(), { target: { value: ZONE_A } })
    expect(highlighted(container)).toEqual(['zone4'])
    fireEvent.change(zoneBox(), { target: { value: ZONE_B } })
    expect(highlighted(container)).toEqual(['zone8'])
    fireEvent.change(zoneBox(), { target: { value: '' } })
    expect(highlighted(container)).toEqual([])
  })

  it('chooses the zone when its area on the map is clicked', async () => {
    mockServer()
    const { container } = render(<App />)
    await postalBox()
    fireEvent.click(container.querySelector('[data-zone="zone8"]')!)
    expect(zoneBox()).toHaveValue(ZONE_B)
    expect(highlighted(container)).toEqual(['zone8'])
  })
})

describe('question types', () => {
  it('shows units for the chosen unit system', async () => {
    mockServer()
    render(<App />)
    await postalBox()
    const area = () => within(screen.getByLabelText('Total floor area')).getAllByRole('option').map((o) => o.textContent)
    expect(area()).toEqual(expect.arrayContaining(AREA_BANDS))
    expect(screen.getByLabelText('Exterior wall thickness (mm)')).toBeInTheDocument()
    fireEvent.click(radio('Preferred units', IMPERIAL))
    expect(area()).toEqual(expect.arrayContaining(AREA_BANDS_FT))
    expect(area()).not.toContain(AREA_BANDS[0])
    expect(screen.getByLabelText('Exterior wall thickness (in)')).toBeInTheDocument()
    expect(screen.getByLabelText('Preferred indoor temperature (°F)')).toBeInTheDocument()
  })

  it('answers floor area, storeys and storeys above ground from a dropdown', async () => {
    mockServer()
    render(<App />)
    await postalBox()
    for (const label of ['Total floor area', 'Number of storeys', 'Number of storeys above ground']) {
      expect(screen.getByLabelText(label).tagName).toBe('SELECT')
    }
    expect(within(screen.getByLabelText('Number of storeys')).getAllByRole('option')).toHaveLength(11) // "Select…" and 1 to 10
  })

  it('shows a follow-up question only after the answer that needs it', async () => {
    mockServer()
    render(<App />)
    await postalBox()
    expect(screen.queryByLabelText(/solar pv capacity/i)).not.toBeInTheDocument()
    fireEvent.click(radio('Existing solar PV installation', 'Yes'))
    expect(screen.getByLabelText(/solar pv capacity.*\(kW\)/i)).toBeInTheDocument()
    fireEvent.click(radio('Existing solar PV installation', 'No'))
    expect(screen.queryByLabelText(/solar pv capacity/i)).not.toBeInTheDocument()
  })

  it('adds and removes renovation records, up to the limit', async () => {
    mockServer()
    render(<App />)
    await postalBox()
    const add = screen.getByRole('button', { name: 'Add renovation' })
    fireEvent.click(add)
    fireEvent.change(screen.getByLabelText('Renovation 1 building element'), { target: { value: 'Roof' } })
    fireEvent.change(screen.getByLabelText('Renovation 1 year'), { target: { value: '2015' } })
    fireEvent.click(add)
    fireEvent.click(add)
    expect(add).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: /remove renovation 1/i }))
    expect(add).toBeEnabled()
    expect(screen.queryByLabelText('Renovation 3 building element')).not.toBeInTheDocument()
  })

  it('shows the household equipment as a dropdown, and lists what is ticked', async () => {
    mockServer()
    render(<App />)
    await postalBox()
    const group = screen.getByRole('group', { name: 'Available household equipment' })
    expect(group.querySelector('details')).not.toBeNull()
    expect(within(group).getByText('Select…')).toBeInTheDocument()
    fireEvent.click(within(group).getByLabelText('Freezer'))
    fireEvent.click(within(group).getByLabelText('Dishwasher'))
    expect(within(group).getByText('2 selected: Freezer, Dishwasher')).toBeInTheDocument()
  })

  it('sends the ticked equipment to the server', async () => {
    const fetchMock = mockServer()
    render(<App />)
    await fillValid()
    fireEvent.click(screen.getByLabelText('Freezer'))
    submit()
    await screen.findByText('Equipment Electrification')
    expect(sentAnswers(fetchMock).household_equipment).toEqual(['Freezer'])
  })

  it('lists the building elements to choose a renovation from', async () => {
    mockServer()
    render(<App />)
    await postalBox()
    fireEvent.click(screen.getByRole('button', { name: 'Add renovation' }))
    const element = screen.getByLabelText('Renovation 1 building element')
    expect(element.tagName).toBe('SELECT')
    expect(within(element).getAllByRole('option').map((o) => o.textContent)).toEqual(['Select…', ...RENOVATION_ELEMENTS])
  })

  it('lets the wall materials be unknown', async () => {
    mockServer()
    render(<App />)
    await postalBox()
    const walls = within(screen.getByRole('group', { name: 'Exterior wall materials' }))
    fireEvent.click(walls.getByLabelText('Unknown'))
    expect(walls.getByText('1 selected: Unknown')).toBeInTheDocument()
  })

  it('asks for details when Other is ticked', async () => {
    mockServer()
    render(<App />)
    await postalBox()
    expect(screen.queryByLabelText(/exterior wall materials: other/i)).not.toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Other'))
    expect(screen.getByLabelText(/exterior wall materials: other/i)).toBeInTheDocument()
  })
})

describe('review and submit', () => {
  it('lists the answers and what is still missing', async () => {
    mockServer()
    render(<App />)
    await postalBox()
    expect(screen.getByText(/still need an answer/i)).toBeInTheDocument()
    await fillValid()
    const review = screen.getByRole('heading', { name: 'Data review and validation' }).closest('section')!
    expect(within(review).getByText('100–150 m²')).toBeInTheDocument() // the band that was chosen, in the review list
    expect(screen.getByText(/everything required is filled in/i)).toBeInTheDocument()
  })

  it('shows what to fix and sends nothing when the form is incomplete', async () => {
    const fetchMock = mockServer()
    render(<App />)
    await postalBox()
    submit()
    expect(screen.getByRole('alert')).toHaveTextContent(/please fix/i)
    expect(fetchMock.mock.calls.some(([url]) => url === '/api/recommend')).toBe(false)
  })

  it('rejects an invalid postal code before sending', async () => {
    const fetchMock = mockServer()
    render(<App />)
    await fillValid()
    fireEvent.change(screen.getByLabelText(/postal code/i), { target: { value: '60601' } })
    submit()
    expect(screen.getByRole('alert')).toHaveTextContent(/character 1 must be a letter/i)
    expect(fetchMock.mock.calls.some(([url]) => url === '/api/recommend')).toBe(false)
  })

  it('sends only the visible, answered questions and shows the recommendation', async () => {
    const fetchMock = mockServer()
    render(<App />)
    await fillValid()
    fireEvent.click(radio('Existing solar PV installation', 'No'))
    submit()
    expect(await screen.findByText('Equipment Electrification')).toBeInTheDocument()
    expect(sentAnswers(fetchMock)).toEqual({
      postal_code: 'N9A 1A1',
      zone: ZONE_A,
      year_built: 1985,
      preferred_units: METRIC,
      floor_area: AREA.A,
      storeys: '2',
      house_type: 'Detached house',
      objectives: ['Reduce energy bills'],
      solar_existing: 'No',
    })
  })

  it('offers programs for the zone and sends the chosen ones', async () => {
    const fetchMock = mockServer()
    render(<App />)
    await fillValid()
    fireEvent.click(radio('Expecting to target government subsidies', 'Yes'))
    fireEvent.click(await screen.findByRole('checkbox', { name: /Program A \(test\)/ }))
    submit()
    await screen.findByText('Equipment Electrification')
    const answers = sentAnswers(fetchMock)
    expect(answers.target_subsidies).toBe('Yes')
    expect(answers.subsidies).toEqual(['Program A (test)'])
  })

  it('clears the chosen programs when the zone changes', async () => {
    mockServer()
    render(<App />)
    await fillValid()
    fireEvent.click(radio('Expecting to target government subsidies', 'Yes'))
    const program = await screen.findByRole('checkbox', { name: /Program A \(test\)/ })
    fireEvent.click(program)
    expect(program).toBeChecked()
    fireEvent.change(zoneBox(), { target: { value: ZONE_B } })
    expect(await screen.findByRole('checkbox', { name: /Program A \(test\)/ })).not.toBeChecked()
  })

  it('shows the problems the server found', async () => {
    mockServer(() =>
      reply({ errors: [{ field: 'floor_area', message: 'Total floor area is outside the allowed range (10 to 5000 m²).' }] }, 422),
    )
    render(<App />)
    await fillValid()
    submit()
    expect(await screen.findByRole('alert')).toHaveTextContent(/outside the allowed range/i)
  })

  it('shows an error message when the backend fails', async () => {
    mockServer(() => reply({}, 500))
    render(<App />)
    await fillValid()
    submit()
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not get a recommendation/i)
  })

  it('shows the server\'s own message when there are too many requests, without blaming the server', async () => {
    const message = 'Too many requests. Please wait a minute and try again.'
    mockServer(() => reply({ errors: [{ field: '', message }] }, 429))
    render(<App />)
    await fillValid()
    submit()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(message)
    expect(alert).not.toHaveTextContent(/is the django server running/i)
    expect(alert).not.toHaveTextContent('429')
  })

  it('clears the too-many-requests message when a later submit works', async () => {
    let calls = 0
    mockServer(() =>
      ++calls === 1
        ? reply({ errors: [{ field: '', message: 'Too many requests. Please wait a minute and try again.' }] }, 429)
        : reply({ package: 'Equipment Electrification' }),
    )
    render(<App />)
    await fillValid()
    submit()
    await screen.findByText(/too many requests/i)
    submit()
    expect(await screen.findByText('Equipment Electrification')).toBeInTheDocument()
    expect(screen.queryByText(/too many requests/i)).not.toBeInTheDocument()
  })
})

describe('climate zone and postal code', () => {
  it('only offers the zones that fit the postal code', async () => {
    mockServer()
    render(<App />)
    fireEvent.change(await postalBox(), { target: { value: 'V6B 1A1' } })
    const options = within(zoneBox()).getAllByRole('option').map((o) => o.textContent)
    expect(options.some((o) => o?.startsWith('Zone 4'))).toBe(true)
    expect(options.some((o) => o?.startsWith('Zone 8'))).toBe(false)
    fireEvent.change(screen.getByLabelText(/postal code/i), { target: { value: 'N9A 1A1' } })
    expect(within(zoneBox()).getAllByRole('option').map((o) => o.textContent).some((o) => o?.startsWith('Zone 8'))).toBe(true)
  })

  it('shows an error and does not submit when the postal code is changed to one the zone does not fit', async () => {
    const fetchMock = mockServer()
    render(<App />)
    await fillValid()
    fireEvent.change(screen.getByLabelText(/postal code/i), { target: { value: 'Y1A 1A1' } })
    expect(screen.getByText(/does not occur where your postal code is/i)).toBeInTheDocument()
    submit()
    expect(fetchMock.mock.calls.some(([url]) => url === '/api/recommend')).toBe(false)
  })

  it('a zone clicked on the map that does not fit the postal code is reported', async () => {
    mockServer()
    const { container } = render(<App />)
    fireEvent.change(await postalBox(), { target: { value: 'V6B 1A1' } })
    fireEvent.click(container.querySelector('[data-zone="zone8"]')!)
    expect(screen.getByText(/does not occur where your postal code is/i)).toBeInTheDocument()
  })
})

describe('years cannot be decimals', () => {
  it('refuses 1985.0 and blocks submitting it', async () => {
    const fetchMock = mockServer()
    render(<App />)
    await fillValid()
    fireEvent.change(yearBox(), { target: { value: '1985.0' } })
    expect(screen.getByText('Enter a whole number.')).toBeInTheDocument()
    submit()
    expect(fetchMock.mock.calls.some(([url]) => url === '/api/recommend')).toBe(false)
  })

  it('sends the year as a whole number', async () => {
    const fetchMock = mockServer()
    render(<App />)
    await fillValid()
    submit()
    await screen.findByText('Equipment Electrification')
    expect(sentAnswers(fetchMock).year_built).toBe(1985)
    expect(JSON.stringify(sentAnswers(fetchMock))).toContain('"year_built":1985,')
  })
})
