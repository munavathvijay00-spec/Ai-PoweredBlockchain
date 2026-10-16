import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';

const baseUrl = process.env.BASE_URL || 'http://127.0.0.1:4173/app/';
const browser = await chromium.launch({ headless: true });
const results = [];

function compactViolation(v) {
  return {
    id: v.id,
    impact: v.impact,
    help: v.help,
    nodes: v.nodes.map(node => ({
      target: node.target,
      html: node.html,
      failureSummary: node.failureSummary,
    })),
  };
}

async function runViewport(name, viewport) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  const consoleErrors = [];
  page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });
  try {
    await page.goto(baseUrl, { waitUntil: 'networkidle', timeout: 60000 });
    const dimensions = await page.evaluate(() => ({
      innerWidth: window.innerWidth,
      scrollWidth: document.documentElement.scrollWidth,
      title: document.title,
    }));
    if (dimensions.scrollWidth > dimensions.innerWidth + 2) {
      throw new Error(`${name}: horizontal overflow ${dimensions.scrollWidth}px > ${dimensions.innerWidth}px`);
    }
    const axe = await new AxeBuilder({ page }).analyze();
    const critical = axe.violations.filter(v => ['critical', 'serious'].includes(v.impact));
    const result = {
      name,
      viewport,
      title: dimensions.title,
      horizontalOverflow: dimensions.scrollWidth - dimensions.innerWidth,
      seriousOrCriticalViolations: critical.map(compactViolation),
      consoleErrors: consoleErrors.slice(0, 10),
    };
    results.push(result);
    if (critical.length) {
      console.error(JSON.stringify({ passed: false, result }, null, 2));
      throw new Error(`${name}: ${critical.length} serious/critical axe violations: ${critical.map(v => v.id).join(', ')}`);
    }
  } finally {
    await context.close();
  }
}

try {
  await runViewport('mobile-375', { width: 375, height: 812 });
  await runViewport('desktop-1440', { width: 1440, height: 1000 });
  console.log(JSON.stringify({ passed: true, results }, null, 2));
} finally {
  await browser.close();
}
