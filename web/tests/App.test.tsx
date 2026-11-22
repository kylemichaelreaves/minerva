import { describe, it, expect, beforeEach, afterEach, vi, type MockedFunction } from "vitest";
import { LANDING_PROMPT_RE } from "~/components/cards/landingPrompts";
import { render, screen, waitFor } from "@solidjs/testing-library";
import { fireEvent } from "./helpers/settledFireEvent";
import App from "~/App";
import { _resetToastsForTesting } from "~/utils/apiError";
import { okResponse } from "./helpers/testRouting";
import { must } from "./helpers/must";

let fetchMock: MockedFunction<typeof fetch>;

function withHash<T>(hash: string, fn: () => T): T {
  const prev = window.location.hash;
  window.history.replaceState(null, "", hash || "#");
  try {
    return fn();
  } finally {
    window.history.replaceState(null, "", prev || "#");
  }
}

describe("<App />", () => {
  beforeEach(() => {
    localStorage.clear();
    _resetToastsForTesting();
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.includes("/api/conversations")) {
        if (url.endsWith("/thread-1")) {
          return Promise.resolve(
            okResponse({
              id: "thread-1",
              title: "Virtue",
              dominant: "P",
              created_at: 1,
              updated_at: 2,
              messages: [
                {
                  role: "user",
                  content: "What is virtue?",
                  created_at: 2,
                  dominant: null,
                  abstained: null,
                  citations: [],
                },
              ],
            }),
          );
        }
        return Promise.resolve(
          okResponse({
            conversations: [
              {
                id: "thread-1",
                title: "Virtue",
                dominant: "P",
                created_at: 1,
                updated_at: 2,
              },
            ],
          }),
        );
      }
      if (url.includes("/api/works")) {
        return Promise.resolve(okResponse({ works: [] }));
      }
      return Promise.resolve(okResponse({}));
    });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    delete document.body.dataset.mobileDrawer;
  });

  it("renders the landing shell on #/", async () => {
    withHash("#/", () => {
      render(() => <App />);
    });
    await waitFor(() => {
      expect(screen.getByPlaceholderText(LANDING_PROMPT_RE)).toBeInTheDocument();
    });
    expect(document.querySelector(".app")).not.toBeNull();
    expect(document.querySelector(".toasts")).not.toBeNull();
    expect(document.querySelector(".sidebar-head")).not.toBeNull();
  });

  it("hydrates a conversation route", async () => {
    withHash("#/c/thread-1", () => {
      render(() => <App />);
    });
    await waitFor(() => {
      expect(screen.getByText("What is virtue?")).toBeInTheDocument();
    });
  });

  it("mounts the request-timing surface on #/metrics", async () => {
    withHash("#/metrics", () => {
      render(() => <App />);
    });
    // The generic `okResponse({})` fallback in this file's fetch mock
    // answers `/api/metrics/summary` with no `rows` key, which exercises
    // the same "nothing recorded yet" path `MetricsPanel.test.tsx` covers
    // directly — this test's job is only the routing wire-up: that
    // `#/metrics` reaches `MetricsRoute` through `AppRoutes`'s new
    // `<Match>`, not the panel's own behavior.
    await waitFor(() => {
      expect(screen.getByText("Observability")).toBeInTheDocument();
    });
  });

  it("opens the delete dialog from the sidebar", async () => {
    withHash("#/", () => {
      render(() => <App />);
    });
    await waitFor(() => {
      expect(document.querySelectorAll(".history-delete").length).toBeGreaterThan(0);
    });
    fireEvent.click(must(document.querySelector(".history-delete")));
    expect(screen.getByText("Delete this conversation?")).toBeInTheDocument();
  });

  it("opens the mobile drawer when matchMedia reports mobile", async () => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes("max-width: 768px"),
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }));

    withHash("#/c/thread-1", () => {
      render(() => <App />);
    });
    await waitFor(() => {
      expect(screen.getByText("What is virtue?")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: "Open menu" }));
    expect(document.body.dataset.mobileDrawer).toBe("open");
  });
});
