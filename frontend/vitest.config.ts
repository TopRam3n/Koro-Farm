import { defineConfig } from "vitest/config";
import path from "path";

// NOTE: This config targets pure TypeScript/logic unit tests (domain selectors, state machines).
// Component tests requiring JSX transforms will be added in Sprint 3+ with the appropriate
// plugin version aligned with the project's vite/next setup.
export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
});
