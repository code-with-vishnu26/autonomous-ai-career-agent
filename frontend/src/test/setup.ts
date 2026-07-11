import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";

// jsdom has no matchMedia implementation; useTheme's initial-theme detection
// needs one to exist at all (its return value is what's under test).
if (!window.matchMedia) {
  window.matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }) as unknown as MediaQueryList;
}

afterEach(() => {
  vi.unstubAllGlobals();
});
