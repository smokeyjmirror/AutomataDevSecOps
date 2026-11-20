const { test, expect } = require('@playwright/test');
const { execFileSync } = require('node:child_process');
const path = require('node:path');

const demoEmail = 'ops@apexlabs.example';
const repositoryRoot = path.resolve(__dirname, '../..');
const demoPauseMs = 4000;

async function pauseForDemo(page) {
  await page.waitForTimeout(demoPauseMs);
}

function createTestSessionCookie() {
  const script = [
    'import json',
    'from app import app',
    'client = app.test_client()',
    'with client.session_transaction() as browser_session:',
    "    browser_session['identity'] = {",
    "        'sub': 'playwright-customer-demo',",
    `        'email': '${demoEmail}',`,
    "        'roles': ['customer'],",
    '    }',
    '    browser_session.permanent = True',
    "cookie = client.get_cookie(app.config['SESSION_COOKIE_NAME'])",
    'if cookie is None:',
    "    raise RuntimeError('Flask did not create a test session cookie')",
    'print(json.dumps({',
    "    'name': app.config['SESSION_COOKIE_NAME'],",
    "    'value': cookie.value,",
    "    'httpOnly': app.config['SESSION_COOKIE_HTTPONLY'],",
    "    'secure': app.config['SESSION_COOKIE_SECURE'],",
    "    'sameSite': app.config['SESSION_COOKIE_SAMESITE'],",
    '}))',
  ].join('\n');

  const output = execFileSync(
    'docker',
    ['compose', 'exec', '-T', 'api', 'python', '-c', script],
    { cwd: repositoryRoot, encoding: 'utf8' }
  );
  return JSON.parse(output.trim());
}

test('Customer Agent checks inventory and follows a request to completion', async ({ page }) => {
  await test.step('Open the portal with a test-only customer session', async () => {
    const cookie = createTestSessionCookie();
    await page.context().addCookies([{
      name: cookie.name,
      value: cookie.value,
      url: 'http://localhost:5000',
      httpOnly: cookie.httpOnly,
      secure: cookie.secure,
      sameSite: cookie.sameSite,
    }]);
    await page.goto('/');
    await expect(page.locator('#identity')).toContainText(demoEmail);
    await pauseForDemo(page);
  });

  await test.step('Ask the Inventory Assistant about low stock', async () => {
    await page.getByLabel('Your question').fill('Which items are low in stock?');
    await page.getByRole('button', { name: 'Ask about inventory' }).click();

    const answer = page.locator('#assistantAnswer');
    await expect(answer).toContainText('Cargo Sensor (SEN-520): 0 in stock');
    await expect(answer).toContainText('no orders were placed');
    await pauseForDemo(page);
  });

  const task = `Customer demo request ${new Date().toISOString()}: prepare an operations status report.`;
  await test.step('Submit a request and watch the worker complete it', async () => {
    await page.locator('#agentId').selectOption({ label: 'Mira — Ops Agent' });
    await page.getByLabel('Task description').fill(task);
    await page.getByRole('button', { name: 'Submit job' }).click();
    await expect(page.locator('#jobMessage')).toHaveText('Request submitted.');
    await pauseForDemo(page);

    const job = page.locator('.job').filter({ hasText: task });
    await expect(job).toContainText('Status: completed', { timeout: 90_000 });
    await pauseForDemo(page);
  });
});
