import { describe, expect, it } from "vitest";
import { render, screen } from "@solidjs/testing-library";
import { LemmaIdentityCard } from "~/Concordance/components/LemmaIdentityCard";
import type { LemmaDetailResponse } from "~/api/concordanceApi";

/** Build a minimal LemmaDetailResponse — only the fields the card reads
 *  (pos_breakdown, gender_breakdown, total). Other facets are empty
 *  arrays since the card doesn't render them. */
function makeDetail(
  overrides: Partial<LemmaDetailResponse> = {},
): LemmaDetailResponse {
  return {
    lemma: "Geist",
    lang: "deu",
    scope: "corpus",
    scope_label: "All German",
    filters: { pos: null, morph: {}, surface: null },
    total: 1247,
    limit: 50,
    offset: 0,
    pos_breakdown: [{ value: "NOUN", count: 1247 }],
    case_breakdown: [],
    number_breakdown: [],
    gender_breakdown: [{ value: "Masc", count: 1247 }],
    surface_breakdown: [],
    work_breakdown: [],
    rows: [],
    next_offset: null,
    ...overrides,
  };
}

describe("<LemmaIdentityCard />", () => {
  it("renders the lemma, POS, lang code, and occurrence count", () => {
    render(() => (
      <LemmaIdentityCard lemma="Geist" lang="deu" data={makeDetail()} />
    ));
    expect(screen.getByText("Geist")).toBeInTheDocument();
    expect(screen.getByText(/NOUN/)).toBeInTheDocument();
    expect(screen.getByText(/DEU/)).toBeInTheDocument();
    expect(screen.getByText("1,247")).toBeInTheDocument();
  });

  it("locks the gender badge at a full share when there's one attested value", () => {
    render(() => (
      <LemmaIdentityCard lemma="Geist" lang="deu" data={makeDetail()} />
    ));
    expect(screen.getByText(/masc/i)).toBeInTheDocument();
    expect(screen.getByText(/100% of attested forms/i)).toBeInTheDocument();
  });

  it("still locks when the dominant gender is ≥95% (spaCy noise tolerance)", () => {
    // Geist's real corpus has Masc 4494 / Fem 38 / Neut 3 — long-tail
    // mislabels. The card should treat that as masculine.
    render(() => (
      <LemmaIdentityCard
        lemma="Geist"
        lang="deu"
        data={makeDetail({
          total: 4535,
          gender_breakdown: [
            { value: "Masc", count: 4494 },
            { value: "Fem", count: 38 },
            { value: "Neut", count: 3 },
          ],
        })}
      />
    ));
    expect(screen.getByText(/masc/i)).toBeInTheDocument();
    expect(screen.getByText(/99\.1% of attested forms/i)).toBeInTheDocument();
  });

  it("does NOT lock when no gender exceeds the 95% threshold", () => {
    // A genuinely ambiguous lemma — e.g. a Latin noun that alternates.
    render(() => (
      <LemmaIdentityCard
        lemma="dies"
        lang="lat"
        data={makeDetail({
          lemma: "dies",
          lang: "lat",
          total: 200,
          pos_breakdown: [{ value: "NOUN", count: 200 }],
          gender_breakdown: [
            { value: "Masc", count: 120 },
            { value: "Fem", count: 80 },
          ],
        })}
      />
    ));
    expect(screen.queryByText(/of attested forms/i)).toBeNull();
  });

  it("handles an empty gender_breakdown without rendering the locked badge", () => {
    // Verbs have no gender at all — the breakdown is empty.
    render(() => (
      <LemmaIdentityCard
        lemma="conferre"
        lang="lat"
        data={makeDetail({
          lemma: "conferre",
          lang: "lat",
          total: 300,
          pos_breakdown: [{ value: "VERB", count: 300 }],
          gender_breakdown: [],
        })}
      />
    ));
    expect(screen.queryByText(/of attested forms/i)).toBeNull();
    expect(screen.getByText(/VERB/)).toBeInTheDocument();
  });
});
