import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/browser",
  timeout: 60000,
  workers: 1,
  retries: 0,
  use: {
    baseURL: "http://127.0.0.1:18765",
    channel: "chrome",
    headless: true,
    viewport: { width: 1440, height: 900 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "..\\.venv\\Scripts\\python.exe ..\\tests\\browser_server.py",
    url: "http://127.0.0.1:18765/api/health",
    reuseExistingServer: false,
    timeout: 30000,
  },
});
