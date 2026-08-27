import { chromium } from 'file:///C:/Users/10741/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs'

const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: 1600, height: 1100 }, deviceScaleFactor: 1 })
page.setDefaultTimeout(10000)

async function open(url) {
  await page.goto('about:blank')
  await page.goto(url, { waitUntil: 'networkidle' })
  await page.waitForSelector('.job-ecosystem-canvas')
}

await open('http://127.0.0.1:8080/#/job-graph?view=portrait')
await page.screenshot({ path: 'work/job-landing-portrait.png', fullPage: true })

await open('http://127.0.0.1:8080/#/job-graph?view=discovery')
console.log('discovery job links', await page.locator('.job-landing-link').count())
await page.locator('.job-landing-link').first().click()
await page.waitForSelector('.job-landing-context')
await page.screenshot({ path: 'work/job-landing-from-discovery.png', fullPage: true })

await open('http://127.0.0.1:8080/#/job-graph?view=ecosystem')
console.log('ecosystem directions', await page.locator('.job-ecosystem-node--direction').count())
await page.locator('.job-ecosystem-node--direction').first().click()
await page.locator('.job-ecosystem-node--category').first().click()
await page.locator('.job-ecosystem-node--cluster').first().click()
console.log('ecosystem job links', await page.locator('.job-landing-link').count())
await page.locator('.job-landing-link').first().click()
await page.waitForSelector('.job-landing-context')
await page.screenshot({ path: 'work/job-landing-from-ecosystem.png', fullPage: true })

await browser.close()
