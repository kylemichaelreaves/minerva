// RTL fixtures for the Reader's Lines component. Phase A foundation
// for Hebrew Masoretic Text and Quran rendering — the corpus content
// flows RTL while line numbers, the xref gutter, and any BCV /
// surah:ayah locators stay LTR-isolated. No backend wiring yet; the
// Hebrew + Arabic strings here are inline fixtures so the design can
// be reviewed before MT / Quran ingest lands.

import type { Meta, StoryObj } from "storybook-solidjs-vite";
import type { SourceChunk } from "~/utils/types";
import { withTheme } from "../../../.storybook/decorators";
import { Lines } from "~/Reader/components/Lines";

// Genesis 1:1–3 (Masoretic Text). Cantillation marks and niqqud
// are included so the font stack's diacritic handling is exercised
// by the fixture.
const HEBREW_GENESIS: SourceChunk[] = [
  {
    chunk_id: "mt-gen-1-1",
    section: "Gen 1:1",
    book: "Genesis",
    page: null,
    speaker: null,
    text:
      "בְּרֵאשִׁ֖ית בָּרָ֣א אֱלֹהִ֑ים אֵ֥ת הַשָּׁמַ֖יִם וְאֵ֥ת הָאָֽרֶץ׃",
    ord: 0,
  },
  {
    chunk_id: "mt-gen-1-2",
    section: "Gen 1:2",
    book: "Genesis",
    page: null,
    speaker: null,
    text:
      "וְהָאָ֗רֶץ הָיְתָ֥ה תֹ֙הוּ֙ וָבֹ֔הוּ וְחֹ֖שֶׁךְ עַל־פְּנֵ֣י תְה֑וֹם וְר֣וּחַ אֱלֹהִ֔ים מְרַחֶ֖פֶת עַל־פְּנֵ֥י הַמָּֽיִם׃",
    ord: 1,
  },
  {
    chunk_id: "mt-gen-1-3",
    section: "Gen 1:3",
    book: "Genesis",
    page: null,
    speaker: null,
    text: "וַיֹּ֥אמֶר אֱלֹהִ֖ים יְהִ֣י א֑וֹר וַֽיְהִי־אֽוֹר׃",
    ord: 2,
  },
];

// Quran Al-Fatiha 1:1–4 (Uthmani script with tashkeel). Surah:ayah
// locators are LTR-isolated by the .surah-ayah / .num rules in
// reader.css so the digits read in their native LTR order.
const ARABIC_FATIHA: SourceChunk[] = [
  {
    chunk_id: "q-1-1",
    section: "1:1",
    book: "Al-Fatiha",
    page: null,
    speaker: null,
    text: "بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ",
    ord: 0,
  },
  {
    chunk_id: "q-1-2",
    section: "1:2",
    book: "Al-Fatiha",
    page: null,
    speaker: null,
    text: "ٱلْحَمْدُ لِلَّهِ رَبِّ ٱلْعَٰلَمِينَ",
    ord: 1,
  },
  {
    chunk_id: "q-1-3",
    section: "1:3",
    book: "Al-Fatiha",
    page: null,
    speaker: null,
    text: "ٱلرَّحْمَٰنِ ٱلرَّحِيمِ",
    ord: 2,
  },
  {
    chunk_id: "q-1-4",
    section: "1:4",
    book: "Al-Fatiha",
    page: null,
    speaker: null,
    text: "مَٰلِكِ يَوْمِ ٱلدِّينِ",
    ord: 3,
  },
];

const meta: Meta<typeof Lines> = {
  title: "Reader/Lines",
  component: Lines,
  parameters: { layout: "fullscreen" },
  decorators: [
    (Story) => (
      <div class="reader" style={{ padding: "32px", "max-width": "760px", margin: "0 auto" }}>
        <Story />
      </div>
    ),
    withTheme("dark"),
  ],
};
export default meta;

type Story = StoryObj<typeof meta>;

export const HebrewMasoretic: Story = {
  name: "RTL — Hebrew (Genesis 1:1–3)",
  args: {
    chunks: HEBREW_GENESIS,
    lang: "heb",
    onWordClick: () => undefined,
  },
};

export const ArabicQuran: Story = {
  name: "RTL — Arabic (Al-Fatiha 1:1–4)",
  args: {
    chunks: ARABIC_FATIHA,
    lang: "ara",
    onWordClick: () => undefined,
  },
};
