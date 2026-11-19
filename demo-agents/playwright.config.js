const { defineConfig } = require('@playwright/test');
const path = require('node:path');
require('dotenv').config({ path: path.resolve(__dirname, '../.env') });

const watchingDemo = process.argv.includes('--headed');

module.exports = defineConfig({
  testDir: './tests',
  timeout: 120_000,
  expect: {
    timeout: 15_000,
  },
  use: {
    baseURL: process.env.AUTOMATA_CLIENT_URL || 'http://localhost:8000',
    launchOptions: {
      slowMo: watchingDemo ? 750 : 0,
    },
  },
  reporter: 'list',
  workers: 1,
});
