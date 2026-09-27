// Atlas data — authors with chronological ordinals, the tradition
// they belong to, an offset row (0/1/2) for label collision avoidance,
// a horizontal label shift in viewBox units, and a one-line work hint
// for the hover tooltip. Ordinals match `src/minerva/author_ordering.py`.

export type Tradition = "scripture" | "classical" | "medieval" | "earlymodern" | "modern";

export interface AtlasAuthor {
  name: string;
  year: number;
  tradition: Tradition;
  row: number;
  xShift: number;
  work: string;
}

// With the atlas widened to ~2400px and horizontally scrollable,
// most authors sit directly under their tick (xShift=0). Row offsets
// kick in only inside the Early Modern cluster, where 8 authors crowd
// into a 120-year span (1640–1760).
// BEGIN ATLAS_AUTHORS
export const ATLAS_AUTHORS: AtlasAuthor[] = [
  {
    name: "Hebrew Bible",
    year: -1000,
    tradition: "scripture",
    row: 0,
    xShift: 28,
    work: "Tanakh — Torah, Nevi'im, Ketuvim",
  },
  { name: "Homer", year: -800, tradition: "classical", row: 0, xShift: 0, work: "Iliad, Odyssey" },
  {
    name: "Theognis",
    year: -540,
    tradition: "classical",
    row: 1,
    xShift: 0,
    work: "Theognidea",
  },
  {
    name: "Aesop",
    year: -580,
    tradition: "classical",
    row: 2,
    xShift: 0,
    work: "Fables (Babrius, Phaedrus)",
  },
  { name: "Thales", year: -600, tradition: "classical", row: 0, xShift: 0, work: "fragments — De principiis" },
  {
    name: "Anaximander",
    year: -580,
    tradition: "classical",
    row: 1,
    xShift: 0,
    work: "On Nature (fragments)",
  },
  { name: "Heraclitus", year: -500, tradition: "classical", row: 0, xShift: 0, work: "On Nature (fragments)" },
  {
    name: "Parmenides",
    year: -490,
    tradition: "classical",
    row: 1,
    xShift: 0,
    work: "On Nature (the Way of Truth)",
  },
  { name: "Plato", year: -380, tradition: "classical", row: 0, xShift: 0, work: "Republic, Symposium, Phaedo" },
  {
    name: "Aristotle",
    year: -340,
    tradition: "classical",
    row: 1,
    xShift: 0,
    work: "Nicomachean Ethics, Metaphysics",
  },
  { name: "Septuagint", year: -250, tradition: "scripture", row: 0, xShift: 0, work: "Greek Old Testament" },
  { name: "Lucretius", year: -55, tradition: "classical", row: 0, xShift: 0, work: "De Rerum Natura" },
  {
    name: "Cicero",
    year: -50,
    tradition: "classical",
    row: 1,
    xShift: 0,
    work: "De Officiis, De Re Publica",
  },
  { name: "New Testament", year: 50, tradition: "scripture", row: 0, xShift: 0, work: "Gospels, Pauline epistles" },
  {
    name: "Epictetus",
    year: 90,
    tradition: "classical",
    row: 1,
    xShift: 0,
    work: "Discourses, Enchiridion",
  },
  { name: "Marcus Aurelius", year: 170, tradition: "classical", row: 0, xShift: 0, work: "Meditations" },
  { name: "Origen", year: 230, tradition: "medieval", row: 0, xShift: 0, work: "Contra Celsum" },
  { name: "Vulgate", year: 400, tradition: "scripture", row: 0, xShift: 0, work: "Latin Bible — Jerome" },
  {
    name: "Augustine",
    year: 430,
    tradition: "medieval",
    row: 1,
    xShift: 0,
    work: "De civitate Dei, Confessiones",
  },
  { name: "Quran", year: 650, tradition: "scripture", row: 0, xShift: 0, work: "al-Qur'ān" },
  { name: "Aquinas", year: 1265, tradition: "medieval", row: 0, xShift: 0, work: "Summa Theologiae" },
  { name: "Luther Bibel 1545", year: 1545, tradition: "scripture", row: 0, xShift: 0, work: "Lutherbibel — Letzte Hand" },
  {
    name: "Luther Bibel 1912",
    year: 1912,
    tradition: "scripture",
    row: 1,
    xShift: 0,
    work: "Lutherbibel — revidiert",
  },
  { name: "King James Bible", year: 1611, tradition: "scripture", row: 0, xShift: 0, work: "Authorized Version" },
  { name: "Sacy", year: 1696, tradition: "scripture", row: 0, xShift: 0, work: "Bible de Port-Royal (Lemaistre de Sacy)" },
  { name: "Descartes", year: 1640, tradition: "earlymodern", row: 0, xShift: 0, work: "Meditationes, Discours de la méthode" },
  {
    name: "Hobbes",
    year: 1651,
    tradition: "earlymodern",
    row: 1,
    xShift: 0,
    work: "Leviathan",
  },
  {
    name: "Pascal",
    year: 1660,
    tradition: "earlymodern",
    row: 2,
    xShift: 0,
    work: "Pensées",
  },
  {
    name: "Spinoza",
    year: 1670,
    tradition: "earlymodern",
    row: 3,
    xShift: 0,
    work: "Ethica, Tractatus",
  },
  {
    name: "Locke",
    year: 1690,
    tradition: "earlymodern",
    row: 4,
    xShift: 0,
    work: "Essay Concerning Human Understanding",
  },
  { name: "Hume", year: 1740, tradition: "earlymodern", row: 0, xShift: 0, work: "Treatise of Human Nature" },
  {
    name: "Boulainvilliers",
    year: 1710,
    tradition: "earlymodern",
    row: 5,
    xShift: 0,
    work: "Histoire de l'ancien gouvernement de la France",
  },
  {
    name: "Rousseau",
    year: 1760,
    tradition: "earlymodern",
    row: 1,
    xShift: 0,
    work: "Du contrat social, Émile",
  },
  {
    name: "Kant",
    year: 1781,
    tradition: "modern",
    row: 2,
    xShift: 0,
    work: "Kritik der reinen Vernunft",
  },
  {
    name: "Schiller",
    year: 1795,
    tradition: "modern",
    row: 1,
    xShift: 0,
    work: "Über die ästhetische Erziehung des Menschen",
  },
  { name: "Hegel", year: 1820, tradition: "modern", row: 0, xShift: 0, work: "Phänomenologie des Geistes" },
  {
    name: "Gobineau",
    year: 1855,
    tradition: "modern",
    row: 3,
    xShift: 0,
    work: "Essai sur l'inégalité des races humaines",
  },
  {
    name: "Renan",
    year: 1863,
    tradition: "modern",
    row: 4,
    xShift: 0,
    work: "Vie de Jésus, L'Antéchrist, Histoire du peuple d'Israël",
  },
  {
    name: "Marx",
    year: 1850,
    tradition: "modern",
    row: 1,
    xShift: 0,
    work: "Kapital, Manuskripte 1844",
  },
  {
    name: "Nietzsche",
    year: 1880,
    tradition: "modern",
    row: 2,
    xShift: 0,
    work: "Also sprach Zarathustra, Genealogie",
  },
];
// END ATLAS_AUTHORS

export const TRADITION_LABEL: Record<Tradition, string> = {
  scripture: "Scripture",
  classical: "Pre-Socratic + Classical",
  medieval: "Patristic + Medieval",
  earlymodern: "Early Modern",
  modern: "Modern",
};

export const Y_MIN = -1000;
// The axis — and the modern band that ends it — runs to the latest author,
// not to a fixed year. It was a fixed 1880 (Nietzsche); Luther Bibel 1912
// then plotted past the end of the line, its tick dangling off the far
// right. Derived so the next later addition can't do the same.
export const Y_MAX = Math.max(1880, ...ATLAS_AUTHORS.map((a) => a.year));

// Band x-ranges (in years) — these drive the 5-colour baseline.
export const BANDS: { key: Tradition; yStart: number; yEnd: number }[] = [
  { key: "scripture", yStart: -1000, yEnd: -850 },
  { key: "classical", yStart: -850, yEnd: 230 },
  { key: "medieval", yStart: 230, yEnd: 1450 },
  { key: "earlymodern", yStart: 1450, yEnd: 1770 },
  { key: "modern", yStart: 1770, yEnd: Y_MAX },
];

// YEAR_TICKS + fmtYear + layoutLabelsGreedy live in the shared
// `utils/atlasGeometry` module so this file (horizontal landing strip)
// and `Network/NetworkArc` (vertical chronology) don't drift apart.
import {
  YEAR_TICKS as SHARED_YEAR_TICKS,
  formatYear,
  layoutLabelsGreedy,
} from "~/utils/atlasGeometry";

export const YEAR_TICKS = SHARED_YEAR_TICKS;
export const fmtYear = formatYear;

// Atlas geometry. The SVG is rendered ~2x wider than the visible
// landing area, so the strip scrolls horizontally — comfortably linear
// chronology in exchange for some right-side scroll.
export const VB_X0 = 60;
export const VB_X1 = 2240;
export const VB_WIDTH = 2280;
export const VB_HEIGHT = 240;
export const BASE_Y = 180;
// Vertical viewBox-unit spacing between stacked author labels. On
// desktop the SVG fits-to-width, so the timeline renders at ~0.48× and
// the dense early-modern cluster (5 rows: Descartes/Hobbes/Pascal/
// Spinoza/Locke + Bible editions) used to overlap visually at the old
// 18-unit gap (~8.6 rendered px between 5px labels). 28 units gives
// ~13.5 rendered px — enough breathing room for the small labels to
// read. Atlas.tsx overrides this with 26 on mobile, where the SVG
// renders at native scale and the cluster is naturally roomier.
export const ROW_GAP = 28;

export function xOf(year: number): number {
  return VB_X0 + ((year - Y_MIN) * (VB_X1 - VB_X0)) / (Y_MAX - Y_MIN);
}

// Pixel-width estimate per character in viewBox units.
export const CHAR_ADVANCE = 0.55;
export const LABEL_PADDING = 6;

/** Greedy row assignment for the horizontal landing strip — thin
 *  adapter over the shared `layoutLabelsGreedy` helper. The shared
 *  helper is axis-agnostic; this binding plugs in the X-axis position
 *  (`xOf(year) + xShift`) and the canonical character-advance
 *  estimate. */
export function assignAtlasRows(
  authors: AtlasAuthor[],
  fontSize: number,
): (AtlasAuthor & { computedRow: number })[] {
  const laid = layoutLabelsGreedy(
    authors,
    (a) => xOf(a.year) + a.xShift,
    (a) => (a.name.length * fontSize * CHAR_ADVANCE) / 2,
    LABEL_PADDING,
  );
  return laid.map(({ item, row }) => ({ ...item, computedRow: row }));
}
