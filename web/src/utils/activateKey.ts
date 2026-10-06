// Enter/Space activation for an element that cannot be a `<button>`: an SVG
// group or path, or a table row (#773). A real button gets this from the
// browser; these need `role`, `tabindex` and this handler to match it.
// `preventDefault` stops Space from also scrolling the page.
export function onActivateKey(activate: () => void): (e: KeyboardEvent) => void {
  return (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    e.preventDefault();
    activate();
  };
}
