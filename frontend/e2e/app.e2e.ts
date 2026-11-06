// End-to-end: the built page in Chromium, the real Django behind it. Nothing is mocked except
// where a test says so (the "server is down" case).
import { expect, test, type Page } from '@playwright/test'

type Field = {
  id: string
  label: string
  type: string
  required: boolean
  options?: string[]
  min?: number
  placement?: string
  show_if?: unknown
}
type Spec = { sections: { fields: Field[] }[] }

const PACKAGES = [
  'No Upgrade Recommended',
  'Equipment Electrification',
  'Basic Envelope + Equipment Electrification',
  'Current Code Envelope + Equipment Electrification',
  'Beyond Code Envelope + Equipment Electrification',
]

// Every problem the browser reports: script errors, console errors, failed loads and anything the
// Content-Security-Policy blocked.
function watchForProblems(page: Page) {
  const problems: string[] = []
  page.on('pageerror', (e) => problems.push(`page error: ${e.message}`))
  page.on('console', (m) => {
    if (m.type() === 'error') problems.push(`console: ${m.text()}`)
  })
  page.on('requestfailed', (r) => problems.push(`failed: ${r.url()} ${r.failure()?.errorText}`))
  page.on('response', (r) => {
    if (r.status() >= 400) problems.push(`HTTP ${r.status()}: ${r.url()}`)
  })
  return problems
}

async function cspViolations(page: Page): Promise<string[]> {
  return page.evaluate(() => (window as unknown as { __csp: string[] }).__csp)
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    const seen: string[] = []
    ;(window as unknown as { __csp: string[] }).__csp = seen
    document.addEventListener('securitypolicyviolation', (e) => seen.push(`${e.violatedDirective} ${e.blockedURI}`))
  })
})

async function realSpec(page: Page): Promise<Field[]> {
  const response = await page.request.get('/api/form-spec')
  expect(response.ok()).toBe(true)
  return ((await response.json()) as Spec).sections.flatMap((s) => s.fields)
}

/** Answers every required question through the page, the way a visitor would. */
async function fillRequired(page: Page, fields: Field[]) {
  for (const f of fields.filter((x) => x.required && !x.show_if)) {
    const box = page.locator(`#f-${f.id}`)
    switch (f.type) {
      case 'text':
        await box.fill(f.id === 'postal_code' ? 'n9a1a1' : 'text') // typed loosely; the page tidies it
        break
      case 'number':
      case 'currency':
        await box.fill(String(f.id === 'year_built' ? 1985 : (f.min ?? 1)))
        break
      case 'select':
        if (f.id === 'zone') {
          await box.selectOption({ label: f.options!.find((o) => o.startsWith('Zone 5:'))! }) // Windsor is in zone 5
        } else {
          await box.selectOption({ label: f.options![0] })
        }
        break
      case 'radio':
        await page.getByRole('group', { name: f.label }).getByRole('radio').first().check()
        break
      case 'checklist':
      case 'multiselect':
        await page.getByRole('group', { name: f.label }).getByRole('checkbox').first().check()
        break
      default:
        throw new Error(`fillRequired does not know how to answer a required ${f.type} question (${f.id})`)
    }
  }
}

test('the built page loads with everything it needs and nothing blocked', async ({ page }) => {
  const problems = watchForProblems(page)
  await page.goto('/')
  await expect(page.getByRole('button', { name: /get my recommendation/i })).toBeVisible()

  const fields = await realSpec(page)
  for (const f of fields.filter((x) => !x.show_if)) {
    await expect(page.getByText(f.label, { exact: false }).first(), f.id).toBeAttached()
  }

  // logo, map and font all actually arrived
  const logo = page.getByRole('img', { name: 'University of Windsor' })
  await expect(logo).toBeVisible()
  expect(await logo.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true)
  expect(await page.locator('path[data-zone]').count()).toBeGreaterThan(0)
  await page.evaluate(() => document.fonts.ready)
  expect(await page.evaluate(() => document.fonts.check('16px Roboto'))).toBe(true)

  expect(problems).toEqual([])
  expect(await cspViolations(page)).toEqual([])
})

test('the built page carries the Content-Security-Policy, and it really blocks injected code', async ({ page }) => {
  await page.goto('/')
  const policy = await page.locator('meta[http-equiv="Content-Security-Policy"]').getAttribute('content')
  expect(policy).toContain("script-src 'self'")
  expect(policy).toContain("object-src 'none'")
  expect(policy).not.toContain('unsafe-inline')
  expect(policy).not.toContain('unsafe-eval')

  // (eval is not tried here: code Playwright injects is exempt from the page's policy, so it would
  // pass either way. The policy text above already proves 'unsafe-eval' is absent.)
  const outcome = await page.evaluate(async () => {
    const w = window as unknown as Record<string, unknown>
    const s = document.createElement('script')
    s.textContent = 'window.__injected = true'
    document.body.appendChild(s)
    const img = document.createElement('img')
    img.src = 'https://example.com/tracker.png'
    document.body.appendChild(img)
    await new Promise((r) => setTimeout(r, 200))
    return { inlineRan: w.__injected === true }
  })
  expect(outcome).toEqual({ inlineRan: false })
  const violations = await cspViolations(page)
  expect(violations.some((v) => v.startsWith('script-src'))).toBe(true)
  expect(violations.some((v) => v.startsWith('img-src') && v.includes('example.com'))).toBe(true)
})

test('the API answers with its own deny-all policy and security headers', async ({ page }) => {
  const response = await page.request.get('/api/form-spec')
  const headers = response.headers()
  expect(headers['content-security-policy']).toContain("default-src 'none'")
  expect(headers['x-frame-options']).toBe('DENY')
  expect(headers['x-content-type-options']).toBe('nosniff')
})

test('a visitor fills in the real form and gets the real server’s recommendation', async ({ page }) => {
  const problems = watchForProblems(page)
  await page.goto('/')
  const fields = await realSpec(page)
  await fillRequired(page, fields)
  await expect(page.locator('#f-postal_code')).toHaveValue('N9A 1A1')

  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith('/api/recommend')),
    page.getByRole('button', { name: /get my recommendation/i }).click(),
  ])
  expect(response.status()).toBe(200)
  const sent = response.request().postDataJSON() as { answers: Record<string, unknown> }
  expect(sent.answers.postal_code).toBe('N9A 1A1')
  expect(sent.answers.year_built).toBe(1985)

  const { package: pkg } = (await response.json()) as { package: string }
  expect(PACKAGES).toContain(pkg)
  await expect(page.locator('.pg-package')).toHaveText(pkg)
  expect(problems).toEqual([])
  expect(await cspViolations(page)).toEqual([])
})

test('the recommendation follows the answers', async ({ page }) => {
  // Scored by recommendations/logic.py: age, glazing, unknown insulation (left unanswered here)
  // and drafty doors add up; an efficient all-electric home needs nothing.
  const recommend = async (year: string, windows: string, fuel: string, cooling: string) => {
    await page.goto('/')
    await fillRequired(page, await realSpec(page))
    await page.locator('#f-year_built').fill(year)
    await page.locator('#f-window_type').selectOption({ label: windows })
    await page.locator('#f-heating_fuel').selectOption({ label: fuel })
    await page.locator('#f-cooling_system').selectOption({ label: cooling })
    await page.getByRole('button', { name: /get my recommendation/i }).click()
    return page.locator('.pg-package')
  }
  await expect(await recommend('1920', 'Single glazing', 'Natural gas', 'Central air conditioner'))
    .toHaveText('Beyond Code Envelope + Equipment Electrification')
  await expect(await recommend('2022', 'Triple glazing', 'Electricity', 'Heat pump'))
    .toHaveText('No Upgrade Recommended')
})

/** Clicks a zone on the map with the real mouse, at a point where that zone is what the visitor sees. */
async function clickZone(page: Page, zoneId: string) {
  const point = await page.evaluate((id) => {
    const path = document.querySelector(`path[data-zone="${id}"]`)!
    const box = path.getBoundingClientRect()
    for (let fy = 0.1; fy < 1; fy += 0.05) {
      for (let fx = 0.1; fx < 1; fx += 0.05) {
        const x = box.left + box.width * fx
        const y = box.top + box.height * fy
        if (document.elementFromPoint(x, y) === path) return { x, y }
      }
    }
    return null
  }, zoneId)
  expect(point, `no visible, clickable point on ${zoneId}`).not.toBeNull()
  await page.mouse.click(point!.x, point!.y)
}

test('clicking a zone on the map chooses it', async ({ page }) => {
  await page.goto('/')
  await page.locator('.cm-svg').scrollIntoViewIfNeeded()
  for (const zone of ['zone8', 'zone4', 'zone6']) {
    await clickZone(page, zone)
    await expect(page.locator('#f-zone')).toHaveValue(new RegExp(`^Zone ${zone.slice(4).toUpperCase()}:`))
    await expect(page.locator(`path[data-zone="${zone}"]`)).toHaveClass(/cm-zone--on/)
  }
})

test('a zone clicked on the map that does not fit the postal code is reported and not sent', async ({ page }) => {
  await page.goto('/')
  await fillRequired(page, await realSpec(page))
  await page.locator('#f-postal_code').fill('C1A 1A1') // Prince Edward Island: never zone 8
  await page.locator('.cm-svg').scrollIntoViewIfNeeded()
  await clickZone(page, 'zone8')
  await expect(page.getByText(/does not occur where your postal code is/i).first()).toBeVisible()

  const recommend: string[] = []
  page.on('request', (r) => {
    if (r.url().endsWith('/api/recommend')) recommend.push(r.url())
  })
  await page.getByRole('button', { name: /get my recommendation/i }).click()
  await expect(page.locator('#f-zone')).toBeFocused()
  expect(recommend).toEqual([])
})

test('an incomplete form is not sent, and the visitor is taken to the first problem', async ({ page }) => {
  await page.goto('/')
  const recommend: string[] = []
  page.on('request', (r) => {
    if (r.url().endsWith('/api/recommend')) recommend.push(r.url())
  })
  await page.getByRole('button', { name: /get my recommendation/i }).click()
  await expect(page.locator('#f-postal_code')).toBeFocused()
  await expect(page.getByText('Postal code is required.').first()).toBeVisible()
  expect(recommend).toEqual([])
})

test('the visitor is told when the server cannot be reached', async ({ page }) => {
  await page.goto('/')
  await fillRequired(page, await realSpec(page))
  await page.route('**/api/recommend', (route) => route.abort('connectionrefused'))
  await page.getByRole('button', { name: /get my recommendation/i }).click()
  await expect(page.getByRole('alert')).toContainText('Could not get a recommendation')
})
