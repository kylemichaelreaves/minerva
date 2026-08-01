// The UD relation inventory the picker offers, and nothing else.
//
// This list is closed on purpose. A mistyped relation is silent data
// corruption: it validates, it exports, and it is wrong — nothing downstream
// will ever tell you. So the picker filters this inventory and never accepts
// free text, and `validateDeprel` refuses anything absent from it.
//
// BOTH SUBTYPE FAMILIES ARE PRESENT, and that is the whole reason the list is
// hand-curated rather than derived from whatever the parser emitted. Stanza's
// German is GSD-trained while the corrected trees are HDT-style: the machine
// writes `obj` and `acl` exactly where a corrector reaches for `expl:pv` and
// `acl:relcl`. Offering one family would mean the correction the user wants
// is not in the list — which is the failure the picker exists to prevent.
//
// Groups follow the UD v2 taxonomy so the list reads in the order a linguist
// expects, not alphabetically.

export interface Relation {
  /** The deprel as it is written to storage and to CoNLL-U. */
  name: string;
  /** One-line gloss, shown beside the name in the picker. */
  gloss: string;
}

export interface RelationGroup {
  title: string;
  relations: Relation[];
}

const g = (title: string, pairs: [string, string][]): RelationGroup => ({
  title,
  relations: pairs.map(([name, gloss]) => ({ name, gloss })),
});

export const RELATION_GROUPS: RelationGroup[] = [
  g("Core arguments", [
    ["nsubj", "nominal subject"],
    ["nsubj:pass", "subject of a passive"],
    ["obj", "direct object"],
    ["iobj", "indirect object"],
    ["csubj", "clausal subject"],
    ["ccomp", "clausal complement"],
    ["xcomp", "open clausal complement"],
  ]),
  g("Non-core dependents", [
    ["obl", "oblique nominal"],
    ["obl:arg", "oblique argument"],
    ["obl:tmod", "temporal modifier"],
    ["advmod", "adverbial modifier"],
    ["advcl", "adverbial clause"],
    ["aux", "auxiliary"],
    ["aux:pass", "passive auxiliary"],
    ["cop", "copula"],
    ["mark", "subordinating marker"],
    ["expl", "expletive"],
    ["expl:pv", "reflexive of a pronominal verb"],
    ["vocative", "vocative"],
    ["discourse", "discourse element"],
    ["dislocated", "dislocated element"],
  ]),
  g("Nominal dependents", [
    ["nmod", "nominal modifier"],
    ["nmod:poss", "possessive modifier"],
    ["amod", "adjectival modifier"],
    ["nummod", "numeric modifier"],
    ["appos", "appositional modifier"],
    ["det", "determiner"],
    ["det:poss", "possessive determiner"],
    ["clf", "classifier"],
    ["case", "case marker"],
    ["acl", "clausal modifier of a noun"],
    ["acl:relcl", "relative clause"],
  ]),
  g("Coordination & multiword", [
    ["conj", "conjunct"],
    ["cc", "coordinating conjunction"],
    ["fixed", "fixed multiword"],
    ["flat", "flat multiword"],
    ["flat:name", "flat — proper name"],
    ["compound", "compound"],
    ["compound:prt", "separable verb particle"],
    ["list", "list"],
    ["parataxis", "parataxis"],
  ]),
  g("Other", [
    ["root", "root of the sentence"],
    ["punct", "punctuation"],
    ["orphan", "orphan (ellipsis)"],
    ["goeswith", "goes with"],
    ["reparandum", "disfluency overridden"],
    ["dep", "unspecified"],
  ]),
];

export const RELATIONS: Relation[] = RELATION_GROUPS.flatMap((group) => group.relations);

const BY_NAME = new Map(RELATIONS.map((r) => [r.name, r]));

export function isKnownRelation(name: string): boolean {
  return BY_NAME.has(name);
}

export function relationGloss(name: string): string | undefined {
  return BY_NAME.get(name)?.gloss;
}

/**
 * The inventory filtered by a substring, keeping group order and dropping
 * groups that end up empty.
 *
 * Substring rather than prefix: a corrector reaching for `expl:pv` types
 * "pv", and a corrector who knows they want a passive types "pass" and wants
 * both `nsubj:pass` and `aux:pass`.
 */
export function filterRelations(query: string): RelationGroup[] {
  const q = query.trim().toLowerCase();
  if (q === "") return RELATION_GROUPS;
  return RELATION_GROUPS.map((group) => ({
    title: group.title,
    relations: group.relations.filter((r) => r.name.includes(q) || r.gloss.includes(q)),
  })).filter((group) => group.relations.length > 0);
}
