import { defineConfig } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

// End-to-end tests run against a separate backend instance with its own temporary database
// (port 8799), so the demo data on 8765 is never touched. Uses the installed Microsoft Edge.
const dbDir = mkdtempSync(join(tmpdir(), "astra-e2e-"));

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: "http://127.0.0.1:8799", headless: true, viewport: { width: 1440, height: 900 } },
  // Installed browsers only (no browser downloads needed): Microsoft Edge and Google Chrome.
  projects: [
    { name: "edge", use: { channel: "msedge" } },
    { name: "chrome", use: { channel: "chrome" } },
  ],
  webServer: {
    command: "..\\backend\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8799 --app-dir ..\\backend",
    cwd: "../backend",
    url: "http://127.0.0.1:8799/api/v1/system/health",
    timeout: 90_000,
    reuseExistingServer: false,
    env: {
      DATABASE_PATH: join(dbDir, "e2e.db"),
      LOCAL_LLM_ENABLED: "false",
      MEDICAL_OFFICER_PIN: "111111",
      ADMIN_PIN: "222222",
      DEMO_CLOCK_SHIFT: "false",
    },
  },
});
