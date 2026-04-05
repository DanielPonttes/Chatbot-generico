const fs = require('fs');
const path = require('path');
const { defineConfig } = require('@playwright/test');

function resolveServerCommand() {
  if (process.env.PLAYWRIGHT_SERVER_CMD) {
    return process.env.PLAYWRIGHT_SERVER_CMD;
  }

  const linuxVenvPython = path.join(__dirname, 'venv', 'bin', 'python');
  const windowsVenvPython = path.join(__dirname, 'venv', 'Scripts', 'python.exe');
  const baseCommand = '-m uvicorn app.main:app --host 127.0.0.1 --port 8012';

  if (fs.existsSync(linuxVenvPython)) {
    return `"${linuxVenvPython}" ${baseCommand}`;
  }

  if (fs.existsSync(windowsVenvPython)) {
    return `"${windowsVenvPython}" ${baseCommand}`;
  }

  return `python ${baseCommand}`;
}

const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8012';

module.exports = defineConfig({
  testDir: './tests/e2e',
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: 'playwright-report' }],
  ],
  use: {
    baseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  webServer: process.env.PLAYWRIGHT_BASE_URL
    ? undefined
    : {
        command: resolveServerCommand(),
        url: `${baseURL}/notifications`,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
        stdout: 'ignore',
        stderr: 'pipe',
      },
});
