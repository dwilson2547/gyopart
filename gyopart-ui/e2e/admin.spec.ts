/**
 * Admin UI end-to-end tests.
 * Tests rules management at http://admin.gyopart-dev.local
 */
import { test, expect } from '@playwright/test'

const ADMIN = 'http://admin.gyopart-dev.local'

test.describe('Admin Rules Page', () => {
  test('rules table has Source and Priority columns', async ({ page }) => {
    await page.goto(`${ADMIN}/admin/ui/rules`)
    await expect(page.getByRole('columnheader', { name: 'Source' })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'Priority' })).toBeVisible()
  })

  test('scope=source reveals source input field', async ({ page }) => {
    await page.goto(`${ADMIN}/admin/ui/rules`)
    // Open the collapsible create form
    await page.getByText('+ Create Rule').click()
    const sourceWrap = page.locator('#rules-source-wrap')
    // Initially hidden via display:none
    await expect(sourceWrap).toHaveCSS('display', 'none')
    // Change scope to source
    await page.locator('select[name="scope"]').selectOption('source')
    await expect(sourceWrap).not.toHaveCSS('display', 'none')
    await expect(page.locator('input[name="source"]')).toBeVisible()
  })

  test('scope=global hides source input field after it was shown', async ({ page }) => {
    await page.goto(`${ADMIN}/admin/ui/rules`)
    await page.getByText('+ Create Rule').click()
    await page.locator('select[name="scope"]').selectOption('source')
    await expect(page.locator('#rules-source-wrap')).not.toHaveCSS('display', 'none')
    await page.locator('select[name="scope"]').selectOption('global')
    await expect(page.locator('#rules-source-wrap')).toHaveCSS('display', 'none')
  })

  test('existing rules have 11 columns per row', async ({ page }) => {
    await page.goto(`${ADMIN}/admin/ui/rules`)
    const tbody = page.locator('#rules-tbody')
    const rowCount = await tbody.locator('tr').count()
    if (rowCount > 0) {
      const cells = tbody.locator('tr').first().locator('td')
      await expect(cells).toHaveCount(11)
    }
  })
})

test.describe('Admin LLM Queue', () => {
  test('LLM queue page loads without server error', async ({ page }) => {
    await page.goto(`${ADMIN}/admin/ui/llm-queue`)
    await expect(page.locator('body')).not.toContainText('Internal Server Error')
    await expect(page.locator('body')).not.toContainText('AttributeError')
    await expect(page.getByRole('heading', { name: /llm rule suggestions/i })).toBeVisible()
  })
})

test.describe('Admin Navigation', () => {
  test('root redirects to discrepancies', async ({ page }) => {
    await page.goto(ADMIN)
    await expect(page).toHaveURL(/discrepancies/)
    await expect(page.locator('body')).not.toContainText('Internal Server Error')
    // Page renders a heading (not an error page)
    await expect(page.locator('h2').first()).toBeVisible()
  })

  test('rules page loads without error', async ({ page }) => {
    await page.goto(`${ADMIN}/admin/ui/rules`)
    await expect(page.locator('body')).not.toContainText('Internal Server Error')
    await expect(page.getByRole('heading', { name: /mapping rules/i })).toBeVisible()
  })

  test('discrepancies page loads', async ({ page }) => {
    await page.goto(`${ADMIN}/admin/ui/discrepancies`)
    await expect(page.locator('body')).not.toContainText('Internal Server Error')
  })
})
