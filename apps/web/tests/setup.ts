import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// vitest.config.ts does not set test.globals, so testing-library's automatic
// afterEach-based cleanup isn't registered implicitly -- without this, DOM
// nodes from earlier renders in the same file leak into later assertions.
afterEach(() => {
  cleanup();
});
