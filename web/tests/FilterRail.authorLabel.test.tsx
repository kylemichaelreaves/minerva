import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@solidjs/testing-library";
import { FilterRail } from "~/Concordance/components/FilterRail";
import type { ConcScope, LemmaDetailResponse } from "~/api/concordanceApi";
import { must } from "./helpers/must";

const DATA: LemmaDetailResponse = {
  lemma: "virtus",
  lang: "lat",
  scope: "corpus",
  scope_label: "Corpus",
  filters: { pos: null, morph: {}, surface: null },
  total: 0,
  limit: 50,
  offset: 0,
  pos_breakdown: [],
  case_breakdown: [],
  number_breakdown: [],
  gender_breakdown: [],
  surface_breakdown: [],
  work_breakdown: [],
  rows: [],
  next_offset: null,
};

function renderRail(scopeAuthors: string[] | undefined, scope: ConcScope = "corpus") {
  const onSetScope = vi.fn();
  const utils = render(() => (
    <FilterRail
      data={DATA}
      scope={scope}
      scopeAuthors={scopeAuthors}
      onSetScope={onSetScope}
      onSetCase={vi.fn()}
      onSetNumber={vi.fn()}
      onSetSurface={vi.fn()}
      onToggleWork={vi.fn()}
      onClearWorks={vi.fn()}
      onResetAll={vi.fn()}
    />
  ));
  const segs = [...utils.container.querySelectorAll(".fr-scope .seg")];
  return { ...utils, onSetScope, authorSeg: must(segs[1], "author segment") };
}

describe("<FilterRail /> author segment label", () => {
  it("prompts 'Author' when no author is scoped, and the segment is inert", () => {
    const { authorSeg, onSetScope } = renderRail(undefined);
    expect(authorSeg.textContent).toBe("Author");
    fireEvent.click(authorSeg);
    expect(onSetScope).not.toHaveBeenCalled();
  });

  it("names the author when exactly one is scoped, and switches scope on click", () => {
    const { authorSeg, onSetScope } = renderRail(["Cicero"]);
    expect(authorSeg.textContent).toBe("Cicero");
    fireEvent.click(authorSeg);
    expect(onSetScope).toHaveBeenCalledWith({ scope: "author" });
  });

  it("counts the authors when several are scoped", () => {
    renderRail(["Cicero", "Seneca", "Livy"], "author");
    expect(screen.getByText("3 authors")).toHaveClass("seg", "on");
  });

  it("counts two authors as '2 authors'", () => {
    const { authorSeg } = renderRail(["Cicero", "Seneca"]);
    expect(authorSeg.textContent).toBe("2 authors");
  });
});
