/**
 * Gyopart UI end-to-end tests.
 * Test vehicle: 2020 Ford EcoSport S 1.0L (car_id=10126) — 1,788 parts
 */
import { test, expect } from '@playwright/test'

const BASE = 'http://gyopart-dev.local'

async function clearState(page: any) {
  await page.goto(BASE)
  await page.evaluate(() => localStorage.removeItem('gyopart_state'))
  await page.reload()
}

async function selectVehicle(page: any) {
  await clearState(page)
  await page.getByRole('combobox', { name: 'Year' }).selectOption('2020')
  await expect(page.getByRole('combobox', { name: 'Make' })).toBeEnabled({ timeout: 5000 })
  await page.getByRole('combobox', { name: 'Make' }).selectOption('Ford')
  await expect(page.getByRole('combobox', { name: 'Model' })).toBeEnabled({ timeout: 5000 })
  await page.getByRole('combobox', { name: 'Model' }).selectOption('EcoSport')
  await expect(page.getByRole('combobox', { name: 'Trim' })).toBeEnabled({ timeout: 5000 })
  await page.getByRole('combobox', { name: 'Trim' }).selectOption('S')
  await expect(page.getByRole('combobox', { name: 'Engine' })).toBeEnabled({ timeout: 5000 })
  await page.getByRole('combobox', { name: 'Engine' }).selectOption({ index: 1 })
  await page.getByRole('button', { name: /set active vehicle/i }).click()
  await expect(page.getByTestId('parts-count')).toBeVisible({ timeout: 10000 })
}

async function openDiagramsTab(page: any) {
  await page.getByRole('button', { name: 'Diagrams' }).click()
  // Wait for the category list to load
  await expect(page.getByRole('button', { name: /body/i })).toBeVisible({ timeout: 8000 })
}

test.describe('Vehicle Picker', () => {
  test('happy path — selects a vehicle and shows parts', async ({ page }) => {
    await selectVehicle(page)
    await expect(page.getByText(/ford ecosport/i)).toBeVisible()
    await expect(page.getByTestId('parts-count')).toContainText('1,788')
  })

  test('dependent selects enable after parent selection', async ({ page }) => {
    await clearState(page)
    const makeSelect = page.getByRole('combobox', { name: 'Make' })
    await expect(makeSelect).toBeDisabled()
    await page.getByRole('combobox', { name: 'Year' }).selectOption('2020')
    await expect(makeSelect).toBeEnabled({ timeout: 5000 })
    await expect(page.getByRole('combobox', { name: 'Model' })).toBeDisabled()
    await makeSelect.selectOption('Ford')
    await expect(page.getByRole('combobox', { name: 'Model' })).toBeEnabled({ timeout: 5000 })
  })

  test('change vehicle — resets to picker', async ({ page }) => {
    await selectVehicle(page)
    await page.getByRole('button', { name: /change/i }).click()
    await expect(page.getByRole('combobox', { name: 'Year' })).toBeVisible()
  })
})

test.describe('Parts List', () => {
  test.beforeEach(async ({ page }) => { await selectVehicle(page) })

  test('shows total count', async ({ page }) => {
    await expect(page.getByTestId('parts-count')).toContainText('1,788')
  })

  test('pagination — next/prev controls', async ({ page }) => {
    await expect(page.getByTestId('page-indicator')).toContainText('Page 1')
    await page.getByTestId('next-page').click()
    await expect(page.getByTestId('page-indicator')).toContainText('Page 2', { timeout: 5000 })
    await page.getByTestId('prev-page').click()
    await expect(page.getByTestId('page-indicator')).toContainText('Page 1', { timeout: 5000 })
  })

  test('filter resets to page 1', async ({ page }) => {
    await page.getByTestId('next-page').click()
    await expect(page.getByTestId('page-indicator')).toContainText('Page 2', { timeout: 5000 })
    await page.getByRole('textbox', { name: /filter parts/i }).fill('sensor')
    await expect(page.getByTestId('page-indicator')).toContainText('Page 1', { timeout: 5000 })
  })

  test('click part selects it', async ({ page }) => {
    const firstPart = page.getByTestId('part-row').first()
    await firstPart.click()
    await expect(firstPart).toHaveClass(/amber/, { timeout: 3000 })
  })

  test('click active part deselects it', async ({ page }) => {
    const firstPart = page.getByTestId('part-row').first()
    await firstPart.click()
    await expect(firstPart).toHaveClass(/amber/, { timeout: 3000 })
    await firstPart.click()
    await expect(firstPart).not.toHaveClass(/amber/, { timeout: 3000 })
  })
})

test.describe('LocalStorage persistence', () => {
  test('selected vehicle survives page reload', async ({ page }) => {
    await selectVehicle(page)
    await page.reload()
    await expect(page.getByText(/ford ecosport/i)).toBeVisible({ timeout: 5000 })
    await expect(page.getByTestId('parts-count')).toContainText('1,788', { timeout: 10000 })
  })

  test('selected part survives page reload', async ({ page }) => {
    await selectVehicle(page)
    const firstPart = page.getByTestId('part-row').first()
    await firstPart.click()
    await expect(firstPart).toHaveClass(/amber/)
    await page.reload()
    await expect(page.getByTestId('parts-count')).toBeVisible({ timeout: 10000 })
    await expect(page.getByTestId('part-row').first()).toHaveClass(/amber/, { timeout: 5000 })
  })
})

test.describe('Diagrams', () => {
  test.beforeEach(async ({ page }) => { await selectVehicle(page) })

  test('Parts/Diagrams tabs appear when vehicle is selected', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Parts' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Diagrams' })).toBeVisible()
  })

  test('Diagrams tab shows category list', async ({ page }) => {
    await openDiagramsTab(page)
    await expect(page.getByRole('button', { name: /body/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /electrical/i })).toBeVisible()
  })

  test('clicking a category shows diagram list', async ({ page }) => {
    await openDiagramsTab(page)
    await page.getByRole('button', { name: /body/i }).click()
    // Wait for diagrams to load — they appear as "Diagram N" buttons
    await expect(page.getByTestId('diagram-entry').first()).toBeVisible({ timeout: 8000 })
  })

  test('clicking a diagram shows image in right panel', async ({ page }) => {
    await openDiagramsTab(page)
    await page.getByRole('button', { name: /body/i }).click()
    await expect(page.getByTestId('diagram-entry').first()).toBeVisible({ timeout: 8000 })
    await page.getByTestId('diagram-entry').first().click()
    await expect(page.locator('img[src*="cloudfront"]')).toBeVisible({ timeout: 15000 })
  })

  test('clicking a diagram part switches to Parts tab', async ({ page }) => {
    await openDiagramsTab(page)
    await page.getByRole('button', { name: /body/i }).click()
    await expect(page.getByTestId('diagram-entry').first()).toBeVisible({ timeout: 8000 })
    await page.getByTestId('diagram-entry').first().click()
    await expect(page.getByText(/click to search junkyards/i)).toBeVisible({ timeout: 15000 })
    await page.getByTestId('diagram-part').first().click()
    // Should switch back to Parts tab — parts-count should be visible
    await expect(page.getByTestId('parts-count')).toBeVisible({ timeout: 5000 })
  })
})

test.describe('Junkyard Search', () => {
  test.beforeEach(async ({ page }) => { await selectVehicle(page) })

  test('ZIP stays populated after changing active part', async ({ page }) => {
    await page.getByTestId('part-row').first().click()
    await page.getByPlaceholder('ZIP code').fill('90210')
    await page.getByTestId('part-row').nth(1).click()
    await expect(page.getByPlaceholder('ZIP code')).toHaveValue('90210')
  })
})

test.describe('Page Title', () => {
  test('top bar shows Gyopart', async ({ page }) => {
    await page.goto(BASE)
    await expect(page.getByText('Gyopart')).toBeVisible()
    await expect(page.getByText('Parts Interchange')).not.toBeVisible()
  })
})
