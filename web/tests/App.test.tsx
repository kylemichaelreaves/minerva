import {
  describe,
  it,
  expect,
  beforeEach,
  afterEach,
  vi,
  type MockedFunction,
} from "vitest";
import { render, screen, fireEvent, waitFor } from "@solidjs/testing-library";
import App from "~/App";
import { _resetToastsForTesting } from "~/utils/apiError";
import { okResponse } from "./helpers/testRouting";

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
      expect(screen.getByPlaceholderText(/what would you like to consider/i)).toBeInTheDocument();
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

  it("opens the delete dialog from the sidebar", async () => {
    withHash("#/", () => {
      render(() => <App />);
    });
    await waitFor(() => {
      expect(document.querySelectorAll(".history-delete").length).toBeGreaterThan(0);
    });
    fireEvent.click(document.querySelector(".history-delete")!);
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
