const { test, expect } = require('@playwright/test');

test('Customer Agent checks inventory and follows a request to completion', async ({ page }) => {
  const username = process.env.DEMO_CUSTOMER_USERNAME;
  const password = process.env.DEMO_CUSTOMER_PASSWORD;
  const email = process.env.DEMO_CUSTOMER_EMAIL || username;

  if (!username || !password) {
    throw new Error(
      'Set DEMO_CUSTOMER_USERNAME and DEMO_CUSTOMER_PASSWORD in the repository .env or export them for a local Keycloak customer.'
    );
  }

  await test.step('Sign in through the local identity provider', async () => {
    await page.goto('/');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await page.locator('#username').fill(username);
    await page.locator('#password').fill(password);
    await page.locator('#kc-login').click();
    await expect(page.locator('#identity')).toContainText(email, { timeout: 30_000 });
  });

  await test.step('Ask the Inventory Assistant about low stock', async () => {
    await page.getByLabel('Your question').fill('Which items are low in stock?');
    await page.getByRole('button', { name: 'Ask about inventory' }).click();

    const answer = page.locator('#assistantAnswer');
    await expect(answer).toContainText('Cargo Sensor (SEN-520): 0 in stock');
    await expect(answer).toContainText('no orders were placed');
  });

  const task = `Customer demo request ${new Date().toISOString()}: prepare an operations status report.`;
  await test.step('Submit a request and watch the worker complete it', async () => {
    await page.locator('#agentId').selectOption({ label: 'Mira — Ops Agent' });
    await page.getByLabel('Task description').fill(task);
    await page.getByRole('button', { name: 'Submit job' }).click();
    await expect(page.locator('#jobMessage')).toHaveText('Request submitted.');

    const job = page.locator('.job').filter({ hasText: task });
    await expect(job).toContainText('Status: completed', { timeout: 90_000 });
  });
});
