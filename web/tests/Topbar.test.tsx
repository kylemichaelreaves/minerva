import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@solidjs/testing-library";
import Topbar from "~/components/Topbar";
import type { Theme } from "~/utils/types";

interface OverrideProps {
  scrolled?: boolean;
  sidebarCollapsed?: boolean;
  theme?: Theme;
  conversationTitle?: string | null | false;
}

function renderTopbar(props: OverrideProps = {}) {
  const onToggleSidebar = vi.fn();
  const onToggleTheme = vi.fn();
  const utils = render(() => (
    <Topbar
      scrolled={props.scrolled ?? false}
      sidebarCollapsed={props.sidebarCollapsed ?? false}
      onToggleSidebar={onToggleSidebar}
      theme={props.theme ?? "light"}
      onToggleTheme={onToggleTheme}
      conversationTitle={props.conversationTitle ?? null}
    />
  ));
  return { onToggleSidebar, onToggleTheme, ...utils };
}

describe("<Topbar />", () => {
  it("shows the placeholder title when no conversation is active", () => {
    renderTopbar();
    expect(screen.getByText(/an untitled enquiry/i)).toBeInTheDocument();
  });

  it("shows the conversation title when one is set", () => {
    renderTopbar({ conversationTitle: "On the nature of justice" });
    expect(screen.getByText(/on the nature of justice/i)).toBeInTheDocument();
  });

  it("does not render the deprecated Socratic-mode toggle", () => {
    renderTopbar();
    expect(screen.queryByRole("button", { name: /socratic/i })).toBeNull();
  });

  it("theme button shows moon in light mode and sun in dark mode", () => {
    const { unmount, onToggleTheme } = renderTopbar({ theme: "light" });
    let btn = screen.getByLabelText(/switch to dark theme/i);
    fireEvent.click(btn);
    expect(onToggleTheme).toHaveBeenCalled();
    unmount();
    renderTopbar({ theme: "dark" });
    btn = screen.getByLabelText(/switch to light theme/i);
    expect(btn).toBeInTheDocument();
  });

  it("shows the sidebar-reveal button only when collapsed", () => {
    const { unmount } = renderTopbar({ sidebarCollapsed: false });
    expect(screen.queryByLabelText(/show sidebar/i)).toBeNull();
    unmount();
    const { onToggleSidebar } = renderTopbar({ sidebarCollapsed: true });
    const btn = screen.getByLabelText(/show sidebar/i);
    fireEvent.click(btn);
    expect(onToggleSidebar).toHaveBeenCalled();
  });
});
