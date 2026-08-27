import { chromium } from 'file:///C:/Users/10741/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs'

const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: 1600, height: 1120 }, deviceScaleFactor: 1 })
page.setDefaultTimeout(60000)

async function open(view) {
  await page.goto('about:blank')
  await page.goto(`http://127.0.0.1:4173/#/job-graph?view=${view}`, { waitUntil: 'networkidle' })
  await page.waitForSelector('.job-ecosystem-canvas')
}

await open('industry')
await page.screenshot({ path: 'work/graph-v05-industry-overview.png', fullPage: true })
const industryDimensions = page.locator('.job-ecosystem-node--dimension')
if (await industryDimensions.count()) {
  await industryDimensions.first().click()
  await page.waitForTimeout(250)
}
const enterprises = page.locator('.job-ecosystem-node--enterprise')
if (await enterprises.count()) {
  await enterprises.first().click()
  await page.waitForTimeout(250)
}
await page.screenshot({ path: 'work/graph-v05-industry-role.png', fullPage: true })

await open('technology')
await page.screenshot({ path: 'work/graph-v05-technology-overview.png', fullPage: true })
const technologySearch = page.locator('.job-ecosystem-search input')
await technologySearch.fill('VLA')
await page.waitForSelector('.job-ecosystem-search-results button')
await page.locator('.job-ecosystem-search-results button').first().click()
await page.waitForTimeout(250)
await page.screenshot({ path: 'work/graph-v05-technology-role.png', fullPage: true })
const technologyJds = page.locator('.standard-role-jd-list .job-landing-link')
if (await technologyJds.count()) {
  await technologyJds.first().click()
  await page.waitForSelector('.full-jd-text')
  await page.screenshot({ path: 'work/graph-v05-technology-jd.png', fullPage: true })
}

await open('portrait')
await page.waitForSelector('.standard-role-profile-canvas')
await page.screenshot({ path: 'work/graph-v05-portrait.png', fullPage: true })

console.log(JSON.stringify({
  industryTabs: await page.locator('.job-three-graph-switch button').count(),
  technologyNodes: await page.locator('.technology-ecosystem-canvas .job-ecosystem-node').count(),
  portraitPoints: await page.locator('.standard-role-profile-canvas .job-ecosystem-node--evidence').count(),
  pageTitle: await page.locator('.page-intro h2').textContent(),
}))

await browser.close()
