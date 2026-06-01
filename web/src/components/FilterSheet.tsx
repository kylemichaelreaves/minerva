import { Show, type JSX } from "solid-js";
import { MobileSheet } from "~/components/MobileSheet";
import { useMobileShell } from "~/components/MobileShellContext";

/** Desktop: inline filters. Mobile: same content in a bottom sheet. */
export function FilterSheet(props: {
  title?: string;
  children: JSX.Element;
}) {
  const shell = useMobileShell();
  return (
    <>
      <Show when={!shell.isMobile()}>{props.children}</Show>
      <MobileSheet
        open={shell.isMobile() && shell.filtersSheetOpen()}
        title={props.title ?? "Filters"}
        onClose={() => shell.setFiltersSheetOpen(false)}
      >
        {props.children}
      </MobileSheet>
    </>
  );
}
