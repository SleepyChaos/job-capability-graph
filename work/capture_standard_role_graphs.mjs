import { chromium } from 'file:///C:/Users/10741/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs'

const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: 1600, height: 1120 }, deviceScaleFactor: 1 })
page.setDefaultTimeout(15000)

async function open(view) {
  await page.goto('about:blank')
  await page.goto(`http://127.0.0.1:8080/#/job-graph?view=${view}`, { waitUntil: 'networkidle' })
  await page.waitForSelector('.job-ecosystem-canvas')
}

await open('ecosystem')
await page.locator('.job-ecosystem-search input').fill('AI算法工程师')
await page.waitForSelector('.job-ecosystem-search-results button')
await page.locator('.job-ecosystem-search-results button').first().click()
await page.waitForSelector('.standard-role-canvas')
await page.screenshot({ path: 'work/standard-role-ecosystem.png', fullPage: true })

const ecosystemJdLinks = page.locator('.standard-role-jd-list .job-landing-link')
if (await ecosystemJdLinks.count()) {
  await ecosystemJdLinks.first().click()
  await page.waitForSelector('.full-jd-text')
  await page.screenshot({ path: 'work/standard-role-jd-evidence.png', fullPage: true })
}

await open('discovery')
await page.screenshot({ path: 'work/standard-role-discovery.png', fullPage: true })

await open('portrait')
console.log('portrait heading', await page.locator('.page-intro h2').textContent())
console.log('portrait canvases', await page.locator('.job-ecosystem-canvas').evaluateAll((nodes) => nodes.map((node) => node.className)))
await page.screenshot({ path: 'work/portrait-debug.png', fullPage: true })
await page.waitForSelector('.standard-role-profile-canvas', { timeout: 30000 })
await page.screenshot({ path: 'work/standard-role-portrait.png', fullPage: true })

const profilePoints = page.locator('.standard-profile-point-list button')
if (await profilePoints.count()) {
  await profilePoints.first().click()
}
const evidenceJobs = page.locator('.standard-role-jd-list .job-landing-link')
if (await evidenceJobs.count()) {
  await evidenceJobs.first().click()
  await page.waitForSelector('.full-jd-text')
  await page.screenshot({ path: 'work/standard-role-portrait-jd.png', fullPage: true })
}

console.log(JSON.stringify({
  ecosystemStandardRoles: await page.locator('.job-ecosystem-node--standardRole').count(),
  profilePoints: await profilePoints.count(),
  fullJdVisible: await page.locator('.full-jd-text').count(),
}))

await browser.close()
