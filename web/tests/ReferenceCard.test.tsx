// Tests for `<ReferenceCard>` — the popover that opens off the
// reader's inline xref marker. Three variants: in-corpus,
// out-of-corpus, and the pending overlay; each exercised here against
// a hand-built `Reference` fixture.

import { describe, it, expect, vi } from "vitest";
import { render, fireEvent } from "@solidjs/testing-library";
import ReferenceCard from "~/components/ReferenceCard";
import type { Reference, ReferenceTarget } from "~/utils/types";

function makeTarget(overrides: Partial<ReferenceTarget> = {}): ReferenceTarget {
  return {
    author: "Aristotle",
    work: "Nicomachean Ethics",
    in_corpus_work_id: 42,
    chunk_id: "ne-1097b",
    locator: "1097b",
    locator_payload: null,
    sort_key: null,
    ...overrides,
  };
}

function makeReference(overrides: Partial<Reference> = {}): Reference {
  return {
    id: 1,
    source_chunk_id: "rep-509d",
    source_span_start: null,
    source_span_end: null,
    source_form: "Aristoteles",
    quoted_phrase: null,
    target: makeTarget(),
    reference_type: "cites",
    confidence: 0.9,
    source_method: "rule+embed+llm",
    curator_status: "approved",
    note: null,
    ...overrides,
  };
}

const ANCHOR = new DOMRect(100, 200, 20, 16);

describe("<ReferenceCard />", () => {
  it("renders target citation with author + italic work + locator", () => {
    const { container } = render(() => (
      <ReferenceCard
        reference={makeReference()}
        anchor={ANCHOR}
        onClose={() => undefined}
      />
    ));
    const head = container.querySelector(".refcard-head");
    expect(head?.textContent).toContain("Aristotle");
    expect(head?.textContent).toContain("Nicomachean Ethics");
    expect(head?.textContent).toContain("1097b");
    expect(head?.querySelector("em")?.textContent).toBe("Nicomachean Ethics");
  });

  it("renders chip with reference_type and 'comments_on' becomes 'comments on'", () => {
    const { container, unmount } = render(() => (
      <ReferenceCard
        reference={makeReference({ reference_type: "comments_on" })}
        anchor={ANCHOR}
        onClose={() => undefined}
      />
    ));
    expect(container.querySelector(".refcard-chip")?.textContent).toBe(
      "comments on",
    );
    unmount();

    const second = render(() => (
      <ReferenceCard
        reference={makeReference({ reference_type: "alludes" })}
        anchor={ANCHOR}
        onClose={() => undefined}
      />
    ));
    expect(second.container.querySelector(".refcard-chip")?.textContent).toBe(
      "alludes",
    );
  });

  it("renders quoted_phrase block when present", () => {
    const { container } = render(() => (
      <ReferenceCard
        reference={makeReference({ quoted_phrase: "estote ergo perfecti" })}
        anchor={ANCHOR}
        onClose={() => undefined}
      />
    ));
    const quote = container.querySelector(".refcard-quote");
    expect(quote?.textContent).toBe("estote ergo perfecti");
    // Latin quote — should NOT carry the Greek class.
    expect(quote?.classList.contains("is-greek")).toBe(false);
  });

  it("tags Greek-script quotes with .is-greek for typographic switching", () => {
    const { container } = render(() => (
      <ReferenceCard
        reference={makeReference({
          quoted_phrase: "Μακάριοι οἱ πτωχοὶ τῷ πνεύματι",
        })}
        anchor={ANCHOR}
        onClose={() => undefined}
      />
    ));
    const quote = container.querySelector(".refcard-quote");
    expect(quote?.classList.contains("is-greek")).toBe(true);
  });

  it("in-corpus variant renders 'Open in reader →' with default hash href", () => {
    const { container } = render(() => (
      <ReferenceCard
        reference={makeReference()}
        anchor={ANCHOR}
        onClose={() => undefined}
      />
    ));
    const open = container.querySelector(
      ".refcard-open",
    );
    expect(open).not.toBeNull();
    expect(open?.textContent).toContain("Open in reader");
    // Default href uses work + ?focus=<chunk_id>.
    expect(open?.getAttribute("href")).toBe(
      "#/r/Nicomachean%20Ethics?focus=ne-1097b",
    );
  });

  it("openInReader prop overrides the default href computation", () => {
    const { container } = render(() => (
      <ReferenceCard
        reference={makeReference()}
        anchor={ANCHOR}
        openInReader={(t) => `/custom/${t.author}`}
        onClose={() => undefined}
      />
    ));
    const open = container.querySelector(".refcard-open");
    expect(open?.getAttribute("href")).toBe("/custom/Aristotle");
  });

  it("out-of-corpus variant renders external-link row instead of 'Open in reader'", () => {
    const { container } = render(() => (
      <ReferenceCard
        reference={makeReference({
          target: makeTarget({
            author: "Cicero",
            work: "De Officiis",
            in_corpus_work_id: null,
            chunk_id: null,
            locator: null,
          }),
        })}
        anchor={ANCHOR}
        onClose={() => undefined}
      />
    ));
    expect(container.querySelector(".refcard-open")).toBeNull();
    const linkRow = container.querySelector(".refcard-ext-links");
    expect(linkRow).not.toBeNull();
    const links = linkRow!.querySelectorAll("a");
    // Default external slot is Logeion / Perseus / archive.org.
    expect(Array.from(links, (a) => a.textContent.trim())).toEqual(
      expect.arrayContaining(["Logeion", "Perseus", "archive.org"]),
    );
    // Logeion URL embeds the encoded author.
    expect(links[0]!.getAttribute("href")).toContain("Cicero");
  });

  it("custom externalLinks override the defaults", () => {
    const { container } = render(() => (
      <ReferenceCard
        reference={makeReference({
          target: makeTarget({ in_corpus_work_id: null, chunk_id: null }),
        })}
        externalLinks={[{ label: "Custom Source", href: "https://example.org" }]}
        anchor={ANCHOR}
        onClose={() => undefined}
      />
    ));
    const links = container.querySelectorAll(".refcard-ext-links a");
    expect(links.length).toBe(1);
    expect(links[0]!.textContent.trim()).toBe("Custom Source");
    expect(links[0]!.getAttribute("href")).toBe("https://example.org");
  });

  it("pending state (curator_status='auto') shows unverified pill + is-pending class", () => {
    const { container } = render(() => (
      <ReferenceCard
        reference={makeReference({ curator_status: "auto" })}
        anchor={ANCHOR}
        onClose={() => undefined}
      />
    ));
    expect(container.querySelector(".refcard.is-pending")).not.toBeNull();
    expect(container.querySelector(".refcard-unverified")?.textContent).toBe(
      "unverified · auto",
    );
  });

  it("Escape calls onClose", () => {
    const onClose = vi.fn();
    render(() => (
      <ReferenceCard
        reference={makeReference()}
        anchor={ANCHOR}
        onClose={onClose}
      />
    ));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("a click away calls onClose", () => {
    // #356: the card's own header comment claimed "Esc / outside-click
    // dismisses" and nothing supplied the second half — `useClickOutside` had
    // six consumers and `useXrefCard` was not one of them. With no close
    // button either (the term card's is error-state only), a reader with this
    // card open had Escape or re-clicking a 24px gutter glyph and nothing
    // else.
    const onClose = vi.fn();
    render(() => (
      <ReferenceCard
        reference={makeReference()}
        anchor={ANCHOR}
        onClose={onClose}
      />
    ));

    fireEvent.mouseDown(document.body);

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("a click on the gutter marker does not call onClose", () => {
    // The marker is the card's anchor, and clicking it again is the
    // toggle-to-dismiss gesture `useXrefCard.onXrefOpen` implements. If the
    // shell counted it as "outside", the mousedown would close the card and
    // the click would then reopen it.
    const onClose = vi.fn();
    const { container } = render(() => (
      <>
        <button class="xref-pin" type="button">
          ▸
        </button>
        <ReferenceCard
          reference={makeReference()}
          anchor={ANCHOR}
          onClose={onClose}
        />
      </>
    ));

    fireEvent.mouseDown(container.querySelector(".xref-pin")!);

    expect(onClose).not.toHaveBeenCalled();
  });

  it("a click inside the card does not dismiss it", () => {
    // What the deleted `stopPropagation()` shim was believed to protect
    // (#357). The protection is containment, in `useClickOutside`
    // (`root.contains(t)`), and it is phase-independent — this test replaces
    // one that asserted the mechanism via a parent handler the app does not
    // have, and asserts the behaviour instead.
    const onClose = vi.fn();
    const { container } = render(() => (
      <ReferenceCard
        reference={makeReference()}
        anchor={ANCHOR}
        onClose={onClose}
      />
    ));

    fireEvent.mouseDown(container.querySelector(".refcard-head")!);

    expect(onClose).not.toHaveBeenCalled();
  });

  it("the close control dismisses the card", () => {
    // #358. This card had no button of any kind before it.
    const onClose = vi.fn();
    const { container } = render(() => (
      <ReferenceCard
        reference={makeReference()}
        anchor={ANCHOR}
        onClose={onClose}
      />
    ));

    fireEvent.click(container.querySelector(".popover-close")!);

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("a click inside the card reaches an ancestor handler", () => {
    // The behaviour change #357 makes: the card is presentation-only, not an
    // event boundary. It used to call `stopPropagation()` on every click,
    // which could not reach the capture-phase `mousedown` listener it named
    // and had no ancestor bubble-phase handler to stop — there is exactly one
    // document-level click-family listener in the app and all six of its call
    // sites are capture-phase. Asserting the bubble keeps the deletion
    // deliberate: if an ancestor handler is ever added, it sees inside-clicks,
    // and this test is where that was decided.
    const parentClick = vi.fn();
    const { container } = render(() => (
      <div onClick={parentClick}>
        <ReferenceCard
          reference={makeReference()}
          anchor={ANCHOR}
          onClose={() => undefined}
        />
      </div>
    ));

    fireEvent.click(container.querySelector(".refcard")!);

    expect(parentClick).toHaveBeenCalledTimes(1);
  });
});
