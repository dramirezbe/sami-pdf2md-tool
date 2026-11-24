import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/desktop",
  workers: 1,
  timeout: 45_000,
  expect: { timeout: 8_000 },
});
