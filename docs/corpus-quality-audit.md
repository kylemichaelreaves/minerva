# Corpus quality audit

Total authors with findings: **41**. Showing top **41** by issue count.


## Summary


| Author | Total | tiny_chunk | mostly_digits | run_on_token | long_s_misread | duplicate_text | glyph_soup | caret_artifact |
|---|---|---|---|---|---|---|---|---|
| Nietzsche | 6,102 | 5,783 | 126 | 1 | 122 | 70 | · | · |
| Hegel | 1,527 | 1,318 | 50 | 12 | 105 | 3 | 30 | 9 |
| Renan | 1,416 | 1,277 | · | 3 | · | 136 | · | · |
| Boulainvilliers | 1,415 | 1,243 | · | 12 | 158 | 2 | · | · |
| Gobineau | 1,091 | 1,056 | · | 11 | 1 | 23 | · | · |
| Kant | 779 | 738 | 4 | · | 30 | 6 | 1 | · |
| Cicero | 582 | 322 | 48 | · | 13 | 109 | 52 | 38 |
| Marx | 560 | 5 | · | 35 | 88 | 426 | · | 6 |
| Descartes | 350 | 132 | · | · | 212 | 6 | · | · |
| Theognis | 293 | 277 | 10 | · | 2 | · | 4 | · |
| Aesop | 219 | 170 | 42 | · | · | · | 2 | 5 |
| Septuagint | 157 | 132 | · | · | · | 24 | · | 1 |
| Quran | 156 | 84 | · | · | · | 72 | · | · |
| King James Bible | 120 | 4 | · | · | · | 116 | · | · |
| Luther Bibel 1912 | 109 | 13 | · | 1 | · | 95 | · | · |
| Luther Bibel 1545 | 108 | 17 | · | 14 | · | 77 | · | · |
| Locke | 107 | 105 | 1 | · | 1 | · | · | · |
| Hebrew Bible | 90 | · | · | · | · | 90 | · | · |
| Sacy | 88 | 32 | · | · | · | 56 | · | · |
| Aristotle | 87 | 70 | · | · | 15 | 2 | · | · |
| Vulgate | 85 | 21 | · | · | · | 64 | · | · |
| Hume | 55 | 53 | 2 | · | · | · | · | · |
| Euripides | 51 | 24 | · | · | 25 | 2 | · | · |
| Marcus Aurelius | 39 | 29 | 6 | · | 3 | · | 1 | · |
| Homer | 35 | · | · | · | 35 | · | · | · |
| New Testament | 19 | 6 | · | · | · | 13 | · | · |
| Aeschylus | 16 | · | · | · | 6 | 10 | · | · |
| Sophocles | 15 | 1 | · | · | 14 | · | · | · |
| Hobbes | 12 | · | · | 12 | · | · | · | · |
| Lucretius | 9 | · | · | · | 9 | · | · | · |
| Empedocles | 7 | 5 | 1 | · | · | · | 1 | · |
| Origen | 7 | · | · | · | 7 | · | · | · |
| Rousseau | 6 | 2 | · | · | 2 | 2 | · | · |
| Epictetus | 6 | 3 | · | · | 3 | · | · | · |
| Plato | 3 | 2 | · | · | 1 | · | · | · |
| Xenophanes | 3 | 3 | · | · | · | · | · | · |
| Pascal | 2 | 1 | 1 | · | · | · | · | · |
| Heraclitus | 2 | 2 | · | · | · | · | · | · |
| Spinoza | 1 | 1 | · | · | · | · | · | · |
| Anaxagoras | 1 | 1 | · | · | · | · | · | · |
| Diogenes of Apollonia | 1 | · | · | · | 1 | · | · | · |

## Triage

Some signals fire on legitimate content — `long_s_misread` over-fires on English texts (real words like *affirmation*, *different*, *effective* hit the pattern), `tiny_chunk` includes structural front-matter (author names, section numbers like ``Vorwort``, ``1``). Use this section to prioritise verified-actionable findings; the per-author samples below let you spot-check before committing to a cleanup pass.

**High-confidence flags worth investigating first:**

- `duplicate_text` with high counts → almost always real (re-ingest residue or Gutenberg/site-chrome bleed)
- `caret_artifact` → real OCR debris (column-edge ^ characters)
- `glyph_soup` (after Hebrew/Arabic skip) → real EPUB image-glyph leakage
- `mostly_digits` → real page-number leakage
- `long_s_codepoint` → real (literal ``ſ`` should be 0)

**Noisier signals — verify samples before acting:**

- `long_s_misread` on **eng** → mostly false positives on real `-ation`/`-ative`/`-iff-` words. Trustworthy on **fra** / **deu**.
- `tiny_chunk` → mix of real noise and legitimate short chunks (author/section names, numbered headings).
- `run_on_token` → catches real PDF-extraction issues but also legitimate long compound words (German *Bundesverfassungsgerichtsentscheidung*).

## Worst-offender samples per (author, signal)

### Nietzsche

**tiny_chunk** (5783+ chunks):
  - `7605bc2071` — 'Friedrich Nietzsche'
  - `6f3feb28fe` — 'Der Antichrist'
  - `549daf797f` — 'Vorwort'
  - `7331ed3207` — '1'
  - `e107a7980e` — '2'

**mostly_digits** (126+ chunks):
  - `829fe447cb` — '[25. Mai] 1865'
  - `3fc8d1cbc5` — '[1009] Basel, 10. Mai 1869'
  - `7cd9f65412` — '[1013] Basel, 28. Sept. 1869'
  - `add7050021` — '[1023] Basel, 21. Mai 1870'
  - `49cd5c9336` — '[1091] Basel, 20. Mai 1873'

**long_s_misread** (122+ chunks):
  - `bd7ba604e0` — 'Endlich, liebster Freund, ist die erste Erregung überwunden, die mir beinahe eine Unverdaulichkeit zugezogen hätte – es wäre doch schade gewesen, wenn ich an di'
  - `aa3c92049d` — 'Nun Deine Schrift, in ihrer Großherzigkeit und kühnen Kriegsgenossenschaft, mitten in das gackernde Völkchen hineinfallend – welches Schauspiel! Romundt und Ove'
  - `cd5ba0ef94` — 'Ja, liebster Freund, Du kommst mir nur um ein klein wenig zuvor, denn als ich meinen letzten Brief an Dich abgelassen, fiel mir erst ein, wie es mit Deiner Zeit'
  - `73730b438b` — 'Ich bin ferne davon, mir es herauszunehmen, Sie zu loben, ebensowenig will ich Sie mit irgendwelchen »Hoffnungen« belästigen, die ich etwa auf Sie setze. Nein! '
  - `0a21296f8a` — 'Fritzsch hat sich bisher noch nicht mit Schmeitzner verständigen können, aber vielleicht kommt es doch noch dazu, da F. großen Wert darauf zu legen scheint, den'

**duplicate_text** (70+ chunks):
  - `a9b4c46551` — '(2 copies) Aber Blut ist der schlechteste Zeuge der Wahrheit; Blut vergiftet die reinste Lehre noch zu Wahn und Haß der Herzen.'
  - `887f531a00` — '(2 copies) An Gustav Krug und Wilhelm Pinder'
  - `8b499742b9` — '(8 copies) An Franziska Nietzsche und Elisabeth Nietzsche'
  - `63ffdb5a7d` — '(2 copies) Dein treuer Freund Fr. Nietzsche'
  - `4b1b66373c` — '(2 copies) An Wilhelm Vischer (-Bilfinger)'

**run_on_token** (1+ chunks):
  - `67bfd7931b` — 'kreuzzeitungsdunstaushauchenden'

### Hegel

**tiny_chunk** (1318+ chunks):
  - `bed08d43a3` — 'Introduction'
  - `218f554b03` — 'on the'
  - `0705a93b72` — 'of'
  - `6dbc5b45e3` — 'VOLUME 1'
  - `f2578fb26f` — '123 124 125'

**long_s_misread** (105+ chunks):
  - `2e007b9499` — '(β) In the same way, ‘ I ’ is the transition from undifferentiated indeterminacy to differentiation, determination , and the positing of a determinacy as a cont'
  - `b635741a1f` — 'The cancellation [ Aufheben ] of crime is retribution in so far as the latter, by its concept, is an infringement of an infringement, and in so far as crime, by'
  - `fd9f6f8aab` — 'The self-consciousness knows how to discover a positive aspect in its own end (see § 135 ); for this end, as part of the purpose of an actual concrete action, n'
  - `3ad044e421` — 'MANUSCRIPTS OF THE INTRODUCTIOr-;; conscience-the silent sancruary where religion has i~ seat-they will not become actually central [to life) but will remain ab'
  - `92088f428a` — 'containing the laws seems to be complete. Later on, w be suce, in more developed conditions, pW1ishments were enacted, although there is no pun- ishment for mur'

**mostly_digits** (50+ chunks):
  - `f2578fb26f` — '123 124 125'
  - `03656acd83` — '1. EL §§ 163 – 165 . 2. Cf. EG § 471.'
  - `8d979b48b1` — '1. Cf. EG § 440.'
  - `2066ad6dbd` — '1. Cf. EG §§ 476–478.'
  - `ae74dbca6c` — '1. Cf. EL §§ 158 – 159 .'

**glyph_soup** (30+ chunks):
  - `750784a108` — '1. Cf. PR § 5 . 2. Cf. PhG ¶¶ 166–167; EG § 424. 3. PhG ¶ 480.'
  - `5ad9025f0a` — '1. Cf. EN §§ 337 – 352 ; EL §§ 213 , 216 and EN § 376; EG § 399.'
  - `ccbd213231` — '1. Cf. PhG ¶¶ 136–139; WL VI , 172–185/518–528; EL §§ 136 – 141 . 2. Cf. Fichte, GNR § 19 , 217–219/299–300.'
  - `23f5f3faa1` — '1. WL VI , 324–326/641–643; cf. § 88, note 1 .'
  - `54dd21d756` — '1. See § 3, note 3 . 2. See § 30, note 1 . 3. See § 137, note 1 .'

**run_on_token** (12+ chunks):
  - `587ace6280` — 'thesubstancewhoseessenceisactuality'
  - `7ddf5a8e09` — 'IthasbeensaidthatthedifferencebetweenNietzscheandHegelisthatwecanunderstand'
  - `e9ab4b6a40` — 'susagetobeconsciousisnotsimplyto'
  - `7a05769bd6` — 'knowledgeisnotonlythegoaloftertiary'
  - `3b9e041569` — 'TopologicalproblemswerecurrentinHegel'

**caret_artifact** (9+ chunks):
  - `21bd6b6e54` — 'Hegel went through a period of self-estrangement to find him- self in the end a pattern of thinking which was to be character- istic of him throughout his life,'
  - `7034470031` — 'Jesus begins the Sermon on the Mount [Matthew v. 2-16] with a species of paradox in which his whole soul forthwith and unam- biguously declares to the multitude'
  - `98878cf1c3` — 'tuality, cancels this leave to divorce, a leave contradictory to that duty. Hence, on the one hand, the sanctity of love is the completion (the xX^pcojLta [fulf'
  - `01eac3917b` — 'God is matter in the form of the Logos : the Logos itself is with God; both are one. The multiplicity, the infinity, of the real is the infinite divisibility re'
  - `322009ae5e` — 'world of men is his very own (t8wv), is most akin to him, and men do not receive him but treat him as a stranger. But those who do recognize themselves in him a'

**duplicate_text** (3+ chunks):
  - `6a37374d4d` — '(2 copies) In memoriam J. Michael Stewart 1920-1994'
  - `8a3ab7009a` — '(2 copies) des Menschen allerhöchste Gaben –'
  - `a6bc2140ee` — '(2 copies) A ist entweder B oder C oder D,'

### Renan

**tiny_chunk** (1277+ chunks):
  - `04fba04dca` — '17-'
  - `3c036e63ef` — 'â'
  - `e95d29e5cc` — '•■n'
  - `8c30ad863e` — 'INTRODUCTION. m'
  - `f23548ba08` — 'Leipzig, 4 872.'

**duplicate_text** (136+ chunks):
  - `d594726399` — '(2 copies) LA RÉFORME INTELLECTUELLE ET MORALE'
  - `930b099a30` — '(2 copies) LETTRES DU SÉMINAIRE (1838-1846)'
  - `e3155c39c2` — '(2 copies) MÉLANGES RELIGIEUX ET HISTORIQUES'
  - `3a8ffd2767` — '(2 copies) FRAGMENTS INTIMES ET ROMANESQUES 1 —'
  - `675586fb4c` — "(3 copies) 2 HISTOIRE DU PEUPLE D'ISRAËL."

**run_on_token** (3+ chunks):
  - `4549876e2a` — 'fautdireautanldeMikahouMikaïahou'
  - `0a6b2a27e9` — 'demandaientunesolutionradicale'
  - `3062ae1c5f` — 'commelesParsissavaientlezenddutempsd'

### Boulainvilliers

**tiny_chunk** (1243+ chunks):
  - `bbd2151300` — 'de France.'
  - `cdc94c416c` — 'vrage. io'
  - `0b160ced1d` — '**'
  - `e5c5a5d79f` — ':'
  - `a66c9ff177` — 'OU FRANÇOIS .'

**long_s_misread** (158+ chunks):
  - `02320a5cc2` — '( 122 ) Colonies sous les Rois de la premiere Race. Voyez à laTable. (23 ) , ( 124 ) Armoriques : Saxons. Voyez àla Table . (125 ) Bajocaffes . Ceux du Païs Bef'
  - `c9de0a3b37` — "après ,& parmi les Seigneurs du Sang royal . Voyez les deux Notes suivantes , Harcourt &Laval à laTable , & pour plus de preuves I'Hift. de la Maison d'Harcourt"
  - `eeb4b6f9aa` — "34 ECU c'est-à-dire , passoient les bras par les guiges , je crois courroye : tenantla poignée avec des gantelets de maille. Fauchet , feüill. 523. Voyez Raguea"
  - `0efc3d9fcc` — 'Ç"I les foins que l\'on s\'ejl donnez pour cette Edition doivent la rendre recommendable, l\'aug- *J ment at ion d\'environ 60 feuilles de plus qu\'on n\'avoit promis'
  - `42d32b40ab` — "de la qualité de ces Ottrois, fe faffent reprefenter les Lettres Patentes & arrefts de Commiflion des deux ou trois derniers Baux, qu'ils en ont fait, les compt"

**run_on_token** (12+ chunks):
  - `4143581b40` — 'duréedecespremieresdominations'
  - `ab15ae2e19` — 'Françoissoubçonnoientaisémentquelque'
  - `1452e39fff` — 'Germainepassoitàunsecondmariage'
  - `b2d1c86b33` — 'éprouvezfurentexemtsdelaTailleàla'
  - `0bbde7ed53` — 'étoientobligezdelessecouriràleursdépens'

**duplicate_text** (2+ chunks):
  - `11c9e8ba8b` — '(4 copies) The Right Honourable the Lord Vifcount'
  - `e6108e31c5` — '(2 copies) The text displayed may contain some errors. The text of this document has been generated automatically by an optical character recognition ('

### Gobineau

**tiny_chunk** (1056+ chunks):
  - `6f6870bcd7` — 'UKS'
  - `190420e330` — "l'Ali"
  - `ea616cd85c` — 'M. A. DE GOBINKAr,'
  - `0e05b250d3` — 'TOME gUATUlKME.'
  - `b7c3c62925` — 'PARIS,'

**duplicate_text** (23+ chunks):
  - `a9cbdc2237` — "(2 copies) Lorsqu'on entrait dans leur résidence, on se trouvait d'abord dans une vaste cour, entourée de divers bâtiments, consacrés à tous les emploi"
  - `d0f5770ead` — '(2 copies) Cependant les nations germaniques, procédant avec la lenteur qui est la condition première de toute œuvre solide, ne devaient pas débuter pa'
  - `83428626fe` — "(2 copies) les avaient à un degré supérieur. Ce fut pour ce motif qu'impuissants dans leur propre cause, ils exercèrent une influence momentanée si con"
  - `5d16d26066` — "(2 copies) Ceux-ci n'eurent garde d'essayer. La manière dont les Visigoths venaient de s'installer était un peu irrégulière; mais une patente impériale"
  - `64b5067372` — "(2 copies) L'esclavage fut donc à peu près aboli sous leur administration (i). Ils le transformèrent en une condition mixte dans laquelle l'homme eut l"

**run_on_token** (11+ chunks):
  - `ad55fcf810` — 'raientprouvéaulantdesoliditéques'
  - `69ccd79c2d` — 'favorablementquelesmailresnoirs'
  - `61209f35c0` — 'IIermanaricdescciidiieiilsurle'
  - `b38a49109e` — 'UMdilTéraiiceftTMluHiDdauiqutU'
  - `e5d7eb412c` — 'coniimtaavacrauréolaciontrimaginaiionenlouraoa'

**long_s_misread** (1+ chunks):
  - `82040cc88f` — 'Toute rex|>ërieiice du paftué réunie pour prou ver que rainalganie de principe» etlmique» déjà ne «aurait fournir une comliinaiiKin rajeunie. (/ei»t déjà beauco'

### Kant

**tiny_chunk** (738+ chunks):
  - `518a7907f5` — 'Immanuel Kant'
  - `b0e1d6e9aa` — 'Vorrede'
  - `2f03c2fc88` — 'Erstes Hauptstück.'
  - `fc73b19fc8` — 'Erklärung 1'
  - `eff3586cd7` — 'Anmerkung 1'

**long_s_misread** (30+ chunks):
  - `4a807df584` — 'Wenn in einem mit Luft angefüllten Stiefel einer Luftpumpe der Kolben dem Boden immer näher getrieben wird, so wird die Luftmaterie zusammengedrückt. Könnte nun'
  - `c77dfbba5b` — 'Die Undurchdringlichkeit, als die Grundeigenschaft der Materie, wodurch sie sich als etwas Reales im Raume unseren äußeren Sinnen zuerst offenbaret, ist nichts,'
  - `2e86a41cbd` — '2. Anziehung, so fern sie bloß als in der Berührung wirksam gedacht wird , heißt Zusammenhang . (Zwar tut man durch sehr gute Versuche dar, daß dieselbe Kraft, '
  - `c830684bf8` — 'Was nun aber das Verfahren in der Naturwissenschaft in Ansehung der vornehmsten aller ihrer Aufgaben, nämlich der Erklärung einer ins Unendliche möglichen spezi'
  - `8af563cd5c` — 'Auf die verschiedenen Begriffe der Bewegung und bewegenden Kräfte haben auch die verschiedenen Begriffe vom leeren Raume ihre Beziehung. Der leere Raum in phoro'

**duplicate_text** (6+ chunks):
  - `5617a98ab2` — '(2 copies) Eben so wenig ist irgend ein Grundsatz der reinen Geometrie analytisch. Daß die gerade Linie zwischen zweien Punkten die kürzeste sei, ist e'
  - `1fc685d62b` — '(2 copies) Die Antinomie der reinen Vernunft'
  - `a1e794bd9d` — '(2 copies) Des Leitfadens der Entdeckung aller reinen Verstandesbegriffe'
  - `743343d0b0` — '(3 copies) Der Antinomie der reinen Vernunft'
  - `d65c8b8a64` — '(2 copies) § 61. Von der objektiven Zweckmäßigkeit der Natur'

**mostly_digits** (4+ chunks):
  - `17c96f4d03` — '[204] (Kritik, S. 341 u. f.)'
  - `e125bb831d` — '[209] (Krit., S. 405 u. f.)'
  - `3b6f5fd210` — '[221] (Kritik, S. 571 u. f.)'
  - `4094abf42d` — 'page [127] [151] [153] [157] [162] [193] [201]'

**glyph_soup** (1+ chunks):
  - `4094abf42d` — 'page [127] [151] [153] [157] [162] [193] [201]'

### Cicero

**tiny_chunk** (322+ chunks):
  - `cb52fff170` — 'and'
  - `52210ae7b7` — 'Of'
  - `02eae7d9e8` — 'M. T. Cicero'
  - `6cda6c0149` — 'With'
  - `89649464cc` — 'C. D. Yonge, B.A.'

**duplicate_text** (109+ chunks):
  - `c795ce65d7` — '(2 copies) V. _A._ To me death seems to be an evil.'
  - `e4d8fe1e57` — '(2 copies) _M._ Then those who have already died, and those who have still got to die, are both miserable?'
  - `5f7bdf98af` — '(2 copies) _M._ And, indeed, if you wish to be consistent, all that are already born, or ever shall be, are not only miserable, but always will be so; '
  - `f17640fb93` — '(2 copies) _M._ Tell me, I beseech you, are you afraid of the three-headed Cerberus in the shades below, and the roaring waves of Cocytus, and the pass'
  - `289fd6814f` — '(2 copies) Who sweats with arduous toil in vain The steepy summit of the mount to gain?'

**glyph_soup** (52+ chunks):
  - `629c0ac978` — '[8] _Ad Fam._ XIII. 16. _T.D._ V. §113. _Acad._ II. §115.'
  - `9dab97cdac` — '[11] _Rep._ I. §7. _T.D._ V. §5. _De Off._ II. §§3,4. _De Fato_, §2.'
  - `f926795e1d` — '[17] Cf. _N.D._ I. §93 with _Ad Fam._ XIII. 1, §1.'
  - `0956e26727` — '[48] _Ad Fam._ XIII. 1. _Ad Att._ V. 11, §6.'
  - `70619329f3` — '[52] Cf. _Tim._ c. 1 with _De Div._ I. §5. _Brutus_, §250.'

**mostly_digits** (48+ chunks):
  - `af56cf9aab` — '39 B.C. 363.'
  - `c332b31976` — '40 B.C. 480.'
  - `2469fafc8c` — 'Sat. x. 361.'
  - `8354030212` — '[28] II. §12.'
  - `0cbe724c16` — '[38] II. 6.'

**caret_artifact** (38+ chunks):
  - `44b50749ca` — '[22] _e quo_ A^1 H a b c, Müller; _eo_ B, _de quo_ Bt. (suppl.), Heine.'
  - `a747bf7757` — '#Fab. inc. (Thyestes?) Vahlen^2, 404#'
  - `3f07c8e934` — '#Ennius, Ann. VI, Vahlen^2, xii, 194-201#'
  - `64a662bfb7` — '[35] _virtuti_ A B^2 L c, Edd.; _virtute_ B^1 H b; _virtutei_ Vahlen.'
  - `465d39803e` — '[40] _diligamur_ A B^2 H L b c; _diligimur_ B^1, Bt^1.'

**long_s_misread** (13+ chunks):
  - `55e14d9e72` — 'For from the same tricks with words, originate all those kingdoms, and commands, and riches, and universal dominion which you say belong to the wise man. You sa'
  - `863128d174` — 'dejected, or sad? Why do you faint, and yield to fortune, which, perhaps, may have power to harass and disturb you, but should not quite unman you? There is gre'
  - `44fefee73d` — 'VII. 25. Nos vero, inquit Atticus: quin etiam Graecis licebit utare, cum voles, si te Latina forte deficient. Bene sane facis: sed enitar ut Latine loquar, nisi'
  - `d401f836c1` — 'XVI. 49. Ad has omnis visiones inanis Antiochus quidem et permulta dicebat et erat de hac una re unius diei disputatio. Mihi autem non idem faciendum puto, sed '
  - `aa15e3bd0e` — '§24. _Natura_: this word, it is important to observe, has to serve as a translation both of φυσις and ουσια. Here it is ουσια in the broadest sense, all that ex'

### Marx

**duplicate_text** (426+ chunks):
  - `19da1dfacd` — '(2 copies) Der achtzehnte Brumaire des Louis Napoleon'
  - `d83f3dcd42` — '(2 copies) Hic Rhodus, hic salta! Hier ist die Rose, hier tanze!'
  - `611fa75fc0` — '(2 copies) Nehmen wir den Faden der Entwicklung wieder auf.'
  - `c4eba1cb69` — '(2 copies) Wir wünschen ihm glückliche Reise.'
  - `a7d68de229` — '(6 copies) Organization: Internet Archive'

**long_s_misread** (88+ chunks):
  - `26bb9b2ad3` — 'Die Periode, die wir vor uns haben, umfaßt das bunteste Gemisch schreiender Widersprüche: Konstitutionelle, die offen gegen die Konstitution konspirieren, Revol'
  - `6b5a1a1b43` — 'Die koalisierten Royalisten spielten ihre Intrige gegeneinander in der Presse, in Ems, in Claremont, außerhalb des Parlaments. Hinter den Kulissen zogen sie ihr'
  - `3203b7a472` — 'Der koalisierten Bourgeoisie gegenüber hatte sich eine Koalition zwischen Kleinbürgern und Arbeitern gebildet, die sogenannte sozial-demokratische Partei. Die K'
  - `bcf295c948` — 'Wie im Jahre 1849 war die Partei der Ordnung während der diesjährigen Parlamentsferien in ihre einzelnen Fraktionen auseinandergegangen, jede beschäftigt mit ih'
  - `bbab62652c` — 'Die Produktion des Lebens, sowohl des eignen in der Arbeit wie des fremden in der Zeugung, erscheint nun schon sogleich als ein doppeltes Verhältnis - einerseit'

**run_on_token** (35+ chunks):
  - `621bffaf3c` — 'Wahlverwandtschaftserscheinung'
  - `0ca32ef688` — 'Proportionalitätsverhältnisses'
  - `3b6b7b6f4b` — 'DisproportionalitätMißverhältnis'
  - `a9ff341084` — 'JurisprudenzRechtswissenschaft'
  - `357e279691` — 'Konstitutionalismusverfassungsmäßige'

**caret_artifact** (6+ chunks):
  - `71bdc25fde` — 'Waare und Geld. 1) Die W aar e. Der Reicbtluuri der Gesellschaften , in welchen kapitalistische Pro- duktionsweise herrscht, erscheint als eine „ungeheure Waare'
  - `56e7ca36a1` — 'Die Verwandlung von Geld in Kai^ital. 1) Dieallgem ein eFormeldes Kapitals. Die Waarencirculation ist der Ausgangspunkt des Kapitals, Waareu- produktion, Waaren'
  - `2a331812f7` — 'Die Produktion des absoluten Mehrwerths. 1) A r b e i t s p r 0 z e s s u n d V e r w e r t h u n g s p r o z e s s. Der Gebrauch der Arbeitskraft ist die Arbei'
  - `277664e67b` — 'Die Produktion des relativen Mehrwerths. 1) B e g r i f f d e s r e 1 a t i V e n Mehrwerths. Der Theil des Arbeitstags, der bloss ein Aequivalent für den vom K'
  - `b7c6fc4cf6` — 'Weitere Untersuchungen über die Produktion des absoluten und relativen Mehrwerths. 1 ) Absoluter und relativer M e h r w e r t h. Der Arbeitsprozess wurde (sieh'

**tiny_chunk** (5+ chunks):
  - `8c2be9ed32` — 'Karl Marx'
  - `365c09342a` — '1. Produktion'
  - `fcb9814519` — '4. Produktion.'
  - `ec4692257d` — 'Karl Marx'
  - `034a29c5b1` — 'GELD'

### Descartes

**long_s_misread** (212+ chunks):
  - `394b4a1298` — "Il est vrai que pour ce qui est des expériences qui peuvent y servir, un homme seul ne saurait suffire à les faire toutes: mais il n'y sauroit aussi employer ut"
  - `f53eefd84e` — 'Et certes je ne vois rien en tout ce que je viens de dire qui ne soit très aisé à connoître par la lumière naturelle à tous ceux qui voudront y penser soigneuse'
  - `262c650929` — "Bien que nous fojons fuffifamment perluadez qu'il y a des corps qui font véritablement dans le monde, neantmoins, comme nous en auons douté cy-deuant% & que nou"
  - `497805208f` — "En ce faifant, nous fçaurons que la nature de la matière, ou du corps pris en gênerai, ne consiste point en ce qu'il ell vne chose dure, ou pefiinte, ou colorée"
  - `dbfbddb6b5` — 'Pour ce qui est de la rarefadion & de la condensation, quiconque voudra examiner les pensées, & ne rien admettre lur ce fujet que ce dont il aura vne idée clair'

**tiny_chunk** (132+ chunks):
  - `76664fbf60` — 'icy proposée.'
  - `6b057ccd4a` — "qu'il contient."
  - `6e9fe4a057` — 'touchant le vuide.'
  - `e1a9aa9dde` — 'Œuvres. IV. 4*'
  - `24e1526d09` — '& innombrables".'

**duplicate_text** (6+ chunks):
  - `be58c64ed0` — '(2 copies) Principes. — Seconde Partie. 85'
  - `49fdafba25` — '(6 copies) Principes. — Troisiesme Partie.'
  - `d3feb886b5` — '(2 copies) b. Correspondance de Descartes, t. V, p. 172.'
  - `b372c4e1d0` — '(2 copies) b. Voir Correspondance, t. V, p. 174.'
  - `5f3c834aa7` — '(6 copies) Principes. — Quatriesme Partie.'

### Theognis

**tiny_chunk** (277+ chunks):
  - `184c7ebf71` — '[Lines 13–26]'
  - `d7a7a3a2ff` — '[Lines 21–48]'
  - `9a66324e91` — '[Lines 49–69]'
  - `16ebb03197` — '[Lines 70–86]'
  - `cdc9a040c0` — '[Lines 87–105]'

**mostly_digits** (10+ chunks):
  - `5868b6cdd7` — '7 ν᾽: lrist. 1. xa. 23, 24,'
  - `589f7dec0f` — '. ix. 454,'
  - `dd7cacd9ab` — 'Cf. Il. iv. 35; xix. 210.'
  - `2581cd55e3` — 'Ion, 1388.'
  - `7d4b2d6c08` — '—For Nestor, see Hom. Od. iii. 244, 126; Il. i. 273; 11. 886, &c.—For -'

**glyph_soup** (4+ chunks):
  - `7d4b2d6c08` — '—For Nestor, see Hom. Od. iii. 244, 126; Il. i. 273; 11. 886, &c.—For -'
  - `cfae20022c` — 'Cf. Matt. Gr. Gr. vol. i. p. 67, § 30 (1832).'
  - `59a794cd88` — 'LXXIV. 247 LXXIV. 247 XLV. 248 + XIV. 248 LXXII. 248 1ΧΧῚ]. 249 XLVIII. 250 XVI. 251'
  - `fae6df2de1` — '[~lines 1370–1379] 1351 (1535) Ὄλβιος, ὃς τις ut 1195.'

**long_s_misread** (2+ chunks):
  - `597d64fc7b` — '‘The hollow-sounding palaces 1015 Of subterraneous gods there in the front Ascend, of mighty Pluto and his queen Awful Persephone. / A grisly dog, Implacable, h'
  - `71dcbec82d` — 'And, when some tusky boar resigns his life, Beneath my darts amid the sylvan strife, Th’ unwieldy victim shall reward your toil, And hungry Cyclops gorge the gr'

### Aesop

**tiny_chunk** (170+ chunks):
  - `ec045a5983` — 'Not here translated'
  - `5d4cd1a15b` — 'Not here translated'
  - `ada0beed08` — 'Not here translated'
  - `b698ba9b23` — 'Not here translated'
  - `323d576fa1` — 'Not here translated'

**mostly_digits** (42+ chunks):
  - `d8901868a9` — '(PIE, 193)'
  - `316217602a` — '(Pp. F. 68.)'
  - `9918a0e946` — '(Pp. ‘F. 10.)'
  - `f7b4a974a6` — '(pr. F. 80.)'
  - `6daacd2537` — '(2. F. 369)'

**caret_artifact** (5+ chunks):
  - `82de36e419` — '[Fable 118] Ξουϑὴ χελιδών, ἣ πάροικος ἀνθρώπων, ἦρος καλιὴν ηὐϑέτιξεν ἐν τοίχῳ, τ 4Ὁ ὅπου γερόντων οἶκος ἦν δικαστήρων᾽" κἀκεῖ νεοσσῶν ἑπτὰ γίνεται μήτηρ. οὔπω '
  - `723eeaabc0` — '[Fable 5] οὗ οὐδὲ A" ΡΥ] ὑπέμεινας A" PT| Epim. simile in A" Pr γατέρων δύω (δυοῖν forma vix Babriana) μήτηρ || 2 sq. &v- (-» αὐτὰς) ἀνδρὶ viv uiv ἀγροίκῳ τὴν δ'
  - `095db35586` — '[Fable 8] βαϑύσχοινος) ἐν χλόῃ βαϑυ- σχοίνῳ (T βαϑυσχένῳ) 46, 2 Baro] σὺν ϑεῷ βαίνεις (6) 92, 6 τὰ πορευτὰ βαίνει 134, 7 ἔμπροσϑεν - τἀξόπισϑε - βαίνει I 34, 12'
  - `ea65b7cf41` — '[Fable 11] διάργεμοι στ. 85, 15 στήλη) ἣν ὁρᾷς στήλην - πα- τρῴη τ᾽ ἐστὶ 81,2 ἠγόραζον (Ερμείην) - εἰς στήλην 30, 2 || στίβη] ἔννυχος στ. 12, 16 στιατός] στικτή'
  - `e641848d92` — '[Fable 10] τένων χρ.; 121, 10 | semper χρήσιμος] oic)w« χρησίμους ὥρας 124, 19 χρηστός] [χρηστὸν ἦϑος 11ῦ, ΤΊ χρηστῶν τ᾽ ἄγγελος “λόγων 95, 13 | τούτων τὸ χρηστ'

**glyph_soup** (2+ chunks):
  - `8112d41f38` — 'ee eee a ————_—_________________ — a —————————'
  - `c671489db6` — '[Fable 2] ὡς χαλήν σε (9) UT 10, 98, 8. 109. 4. 182, Τ εὐ ἥσει (e) 12, 17 sim. 127, 4 ὅστις σ᾽ ἐλαφρὴν - ϑήσω 115,6 etc. | καὶ σὲ (2γγράφειν 15,1809? 6£ (5), τὸ'

### Septuagint

**tiny_chunk** (132+ chunks):
  - `5045f4d33f` — 'υἱοὶ δὲ Δάν· Ἁσόμ.'
  - `644fb91171` — 'καὶ υἱοὶ Ἰσσαάρ·'
  - `ae1675f874` — 'XX'
  - `8777c44baa` — 'Οὐ σεῖς.'
  - `d527a1de06` — 'Οὐ κλέψεις. (13)'

**duplicate_text** (24+ chunks):
  - `a7d46a8b2e` — '(2 copies) Καὶ εἶπεν κύριος πρὸς Μωυσῆν καὶ Ἀαρὼν λέγων'
  - `d09eb57d94` — '(7 copies) καὶ ἐλάλησεν κύριος πρὸς Μωυσῆν λέγων'
  - `db887f43fe` — '(5 copies) καὶ ἐλάλησεν Κύριος πρὸς Μωυσῆν λέγων'
  - `ae6c206841` — '(2 copies) Οὐ ποιήσεις σεαυτῷ εἴδωλον οὐδὲ παντὸς ὁμοίωμα, ὅσα ἐν τῷ οὐρανῷ ἄνω καὶ ὅσα ἐν τῇ γῇ κάτω καὶ ὅσα ἐν τοῖς ὕδασιν ὑποκάτω τῆς γῆς.'
  - `33059ce343` — '(30 copies) Καὶ ἐλάλησεν κύριος πρὸς Μωυσῆν λέγων'

**caret_artifact** (1+ chunks):
  - `70ba8a8a60` — 'ἐγένετο μετὰ τὴν ἐπαύριον συνεκάθισεν μυσῆς κρίνειν τὸν λαόν· παρειστήκει δὲ πᾶς ὁ λαὸς Mcovo^fl ἀπὸ πρωίθεν ἕως δείλης.'

### Quran

**tiny_chunk** (84+ chunks):
  - `71c48db609` — 'الٓمٓ'
  - `8357fdd2ec` — 'الٓمٓ'
  - `4861a07dfa` — 'الٓمٓصٓ'
  - `393e1ea416` — 'فَأَتْبَعَ سَبَبًا'
  - `539ac3374f` — 'كٓهيعٓصٓ'

**duplicate_text** (72+ chunks):
  - `963f3d81d8` — '(2 copies) أُو۟لَٰٓئِكَ عَلَىٰ هُدًى مِّن رَّبِّهِمْ ۖ وَأُو۟لَٰٓئِكَ هُمُ ٱلْمُفْلِحُونَ'
  - `6a1f1f2eef` — '(2 copies) يَٰبَنِىٓ إِسْرَٰٓءِيلَ ٱذْكُرُوا۟ نِعْمَتِىَ ٱلَّتِىٓ أَنْعَمْتُ عَلَيْكُمْ وَأَنِّى فَضَّلْتُكُمْ عَلَى ٱلْعَٰلَمِينَ'
  - `2e9f946f7f` — '(2 copies) تِلْكَ أُمَّةٌ قَدْ خَلَتْ ۖ لَهَا مَا كَسَبَتْ وَلَكُم مَّا كَسَبْتُمْ ۖ وَلَا تُسْـَٔلُونَ عَمَّا كَانُوا۟ يَعْمَلُونَ'
  - `1fc74f6ee8` — '(2 copies) إِلَّا ٱلَّذِينَ تَابُوا۟ مِنۢ بَعْدِ ذَٰلِكَ وَأَصْلَحُوا۟ فَإِنَّ ٱللَّهَ غَفُورٌ رَّحِيمٌ'
  - `2f7aa369b6` — '(2 copies) وَٱلَّذِينَ كَفَرُوا۟ وَكَذَّبُوا۟ بِـَٔايَٰتِنَآ أُو۟لَٰٓئِكَ أَصْحَٰبُ ٱلْجَحِيمِ'

### King James Bible

**duplicate_text** (116+ chunks):
  - `672b1322a2` — '(2 copies) The sons of Japheth; Gomer, and Magog, and Madai, and Javan, and Tubal, and Meshech, and Tiras.'
  - `9a87a6e8ff` — '(2 copies) And the sons of Javan; Elishah, and Tarshish, Kittim, and Dodanim.'
  - `b8ca82b92e` — '(2 copies) And Mizraim begat Ludim, and Anamim, and Lehabim, and Naphtuhim,'
  - `c38702349c` — '(2 copies) And the Hivite, and the Arkite, and the Sinite,'
  - `4829ef4907` — '(2 copies) And Joktan begat Almodad, and Sheleph, and Hazarmaveth, and Jerah,'

**tiny_chunk** (4+ chunks):
  - `667f60531c` — 'Adam, Sheth, Enosh,'
  - `b49d335232` — 'Eber, Peleg, Reu,'
  - `2adc505c29` — 'Jesus wept.'
  - `6921d4f5e0` — 'Rejoice evermore.'

### Luther Bibel 1912

**duplicate_text** (95+ chunks):
  - `44636c564c` — '(2 copies) Mizraim zeugte die Luditer, die Anamiter, die Lehabiter, die Naphthuhiter,'
  - `3a1369676e` — '(2 copies) den Jebusiter, den Amoriter, den Girgasiter,'
  - `e694e82f51` — '(2 copies) den Heviter, den Arkiter, den Siniter,'
  - `b7bfa23def` — '(2 copies) und lebte darnach vierhundertunddrei Jahre und zeugte Söhne und Töchter.'
  - `a42791247a` — '(68 copies) Und der HERR redete mit Mose und sprach:'

**tiny_chunk** (13+ chunks):
  - `58d97666e9` — 'Misma, Duma, Massa,'
  - `0ca378142b` — 'Amam, Sema, Molada,'
  - `03ca5d6b14` — 'Baala, Ijim, Ezem,'
  - `aa3cfef770` — 'Libna, Ether, Asan,'
  - `c4a2d96d37` — 'Arab, Duma, Esean,'

**run_on_token** (1+ chunks):
  - `a9b95eda76` — 'hundertsiebenundfünfzigtausend'

### Luther Bibel 1545

**duplicate_text** (77+ chunks):
  - `133a6ccf08` — '(2 copies) Du sollst kein falsch Zeugnis reden wider deinen Nächsten.'
  - `643cfd6c12` — '(2 copies) Also fiel Israel ab vom Hause Davids bis auf diesen Tag.'
  - `1b06609faf` — '(2 copies) der Kinder Ater von Hiskia achtundneunzig;'
  - `87037e27bb` — '(2 copies) der Kinder Immer tausend und zweiundfünfzig;'
  - `a0f08db4d8` — '(2 copies) die Kinder Bakbuk, die Kinder Hakupha, die Kinder Harhur,'

**tiny_chunk** (17+ chunks):
  - `c2108ed9eb` — 'Hivi, Arki, Sini,'
  - `8bb5525026` — 'Misma, Duma, Masa,'
  - `80c35ac9db` — 'Amam, Sema, Molada,'
  - `7b0ff777f2` — 'Baala, Ijim, Azem,'
  - `8d3a3f6a43` — 'Libna, Ether, Asan,'

**run_on_token** (14+ chunks):
  - `25daf54bab` — 'siebenhundertsiebenundsiebenzig'
  - `09543a472b` — 'tausendsiebenhundertfünfundsiebenzig'
  - `d7cbcebf82` — 'dreitausendfünfhundertundfünfzig'
  - `f776c2c7a6` — 'siebenhundertundfünfundsiebenzig'
  - `554fe5012e` — 'hundertundsechsundachtzigtausend'

### Locke

**tiny_chunk** (105+ chunks):
  - `f058d410fa` — 'By John Locke'
  - `4d0ab5a45c` — '[image]'
  - `d2e1c1e05e` — 'MDCXC'
  - `5295f41d8c` — '2. Design.'
  - `e9d359eb04` — '3. Method.'

**mostly_digits** (1+ chunks):
  - `38333f520e` — 'Units. 623137'

**long_s_misread** (1+ chunks):
  - `9fe0718ce9` — 'This is so far from being a restraint or diminution of freedom, that it is the very improvement and benefit of it; it is not an abridgment, it is the end and us'

### Hebrew Bible

**duplicate_text** (90+ chunks):
  - `5b30940df7` — '(2 copies) וְֽאֶת ־ פַּתְרֻסִ֞ים וְאֶת ־ כַּסְלֻחִ֗ים אֲשֶׁ֨ר יָצְא֥וּ מִשָּׁ֛ם פְּלִשְׁתִּ֖ים וְאֶת ־ כַּפְתֹּרִֽים ׃ ס'
  - `2aa7d89801` — '(2 copies) וְאֶת ־ הַיְבוּסִי֙ וְאֶת ־ הָ֣אֱמֹרִ֔י וְאֵ֖ת הַגִּרְגָּשִֽׁי ׃'
  - `0601ce7c0a` — '(2 copies) וְאַרְפַּכְשַׁ֖ד יָלַ֣ד אֶת ־ שָׁ֑לַח וְשֶׁ֖לַח יָלַ֥ד אֶת ־ עֵֽבֶר ׃'
  - `39442acb8a` — '(2 copies) וְיָקְטָ֣ן יָלַ֔ד אֶת ־ אַלְמוֹדָ֖ד וְאֶת ־ שָׁ֑לֶף וְאֶת ־ חֲצַרְמָ֖וֶת וְאֶת ־ יָֽרַח ׃'
  - `3149a138b1` — '(2 copies) וְאֶת ־ הֲדוֹרָ֥ם וְאֶת ־ אוּזָ֖ל וְאֶת ־ דִּקְלָֽה ׃'

### Sacy

**duplicate_text** (56+ chunks):
  - `fdf9c53587` — '(32 copies) Le Seigneur parla encore à Moïse, et lui dit :'
  - `347fec112a` — '(2 copies) Or le Seigneur parla à Moïse, et lui dit :'
  - `5a56fd2ae1` — '(2 copies) Vous ne commettrez point de fornication.'
  - `7291fc684b` — '(2 copies) Vous ne porterez point de faux témoignage contre votre prochain.'
  - `9544d9671b` — '(2 copies) Le Seigneur parla encore à Moïse et lui dit :'

**tiny_chunk** (32+ chunks):
  - `f47f7e423b` — 'Masma, Duma, Massa,'
  - `ddc207233a` — 'Qui lui dit :'
  - `0963b770fd` — 'Et il dit à Josué :'
  - `9af03adbad` — 'Amam, Sama, Molada,'
  - `53cf4e423c` — 'Baala, Jim, Ésem,'

### Aristotle

**tiny_chunk** (70+ chunks):
  - `089d99f9b3` — 'And in some cases'
  - `6d3e29200c` — 'καὶ τὸ'
  - `6b91693b02` — 'καὶ ἐν ἄλλοις'
  - `1d48d41ba8` — 'καὶ τὸ'
  - `2c888071c3` — 'SECTION 2'

**long_s_misread** (15+ chunks):
  - `a6cfb450c1` — 'Between Housecraft (the art of governing a Household or Home) and Statecraft (the art of governing a Nation) there are differences corresponding to those betwee'
  - `e7cd3ecb44` — 'In general it does not matter whether it contains many or few terms, nor, therefore, whether it contains few or two. Of the two one is differentia and the other'
  - `3a706ae962` — 'and which is not accidentally differentiated, whether regarded as matter or otherwise. For not only must the common quality belong to both, e.g., that they are '
  - `a784022583` — 'Indeed the fact that an offence was committed in ignorance is itself made a ground for punishment, in cases where the offender is held to be responsible for his'
  - `639804537d` — 'Another topic is derived from relative terms. For if to have done rightly or justly may be predicated of one, then to have suffered similarly may be predicated '

**duplicate_text** (2+ chunks):
  - `307dbc8119` — '(15 copies) Copyright statement: The Internet Classics Archive by Daniel C. Stevenson, Web Atomics. World Wide Web presentation is copyright (C) 1994-20'
  - `862af49ae5` — '(2 copies) Those that depend upon the assumption of the original point and upon stating as the cause what is not the cause, are clearly shown to be cas'

### Vulgate

**duplicate_text** (64+ chunks):
  - `38c726c1b8` — '(6 copies) Gratia vobis, et pax a Deo Patre nostro, et Domino Jesu Christo.'
  - `0e5b1e7493` — '(2 copies) dux Oolibama, dux Ela, dux Phinon,'
  - `6d07d112c8` — '(2 copies) dux Cenez, dux Theman, dux Mabsar,'
  - `68f7cf1df2` — '(2 copies) Filius autem Jonathan, Meribbaal : et Meribbaal genuit Micha.'
  - `d95ed6b273` — '(2 copies) dicens : Tibi dabo terram Chanaan, funiculum hæreditatis vestræ :'

**tiny_chunk** (21+ chunks):
  - `8c09e99017` — 'Adam, Seth, Enos,'
  - `9469741b8b` — 'Eliphal filius Ur,'
  - `94b0fb693a` — 'Semper gaudete.'
  - `778500f516` — 'Non occides,'
  - `43d7363b4a` — 'neque m\x9cchaberis,'

### Hume

**tiny_chunk** (53+ chunks):
  - `421d7b662b` — 'INDEX'
  - `79c77fb18b` — '[2] Resemblance.'
  - `fa73595252` — '[3] Contiguity.'
  - `80ef3edc39` — 'OF PROBABILITY[9].'
  - `ab90e04b37` — '[10] Section II.'

**mostly_digits** (2+ chunks):
  - `9e061ac415` — 'A priori 25, 36 n, 89 n, 132, 132 n.'
  - `882c560f6e` — 'Faith 101, 132.'

### Euripides

**long_s_misread** (25+ chunks):
  - `c0df7bf036` — 'Behold I bring thy son with me, whom thou didst steal away to a neighbour’s house without my daughter’s knowledge. Thou wert so sure this image of the goddess w'
  - `c6940ab2e5` — 'Thou hast left me, O my father, left me like a stranded bark, all alone, without an oar. My lord will surely slay me; no home is mine henceforth beneath my husb'
  - `ec83bdae1e` — 'Who is at the gates? Call from the house Kadmos, son of Agenor, who leaving the city of Sidon built this towering city of the Thebans. Let someone go and announ'
  - `ddba2fad03` — 'Who is here, who? From what quarter did the voice of the Joyful one summon me? Io! Io! I say again; it is I, the child of Zeus and Semele. Io! Io! Master, maste'
  - `81bfbe0415` — 'Oh house once fortunate in Hellas , house of the Sidonian old man who once sowed in the ground the earth-born harvest of the serpent Ophis, how I groan for you,'

**tiny_chunk** (24+ chunks):
  - `88e2b24084` — 'Ah me! alas!'
  - `5b657be98d` — 'Alas, O house!'
  - `b01be5fbb0` — 'Woe to these halls!'
  - `7925febdd6` — 'Ah misery!'
  - `564625b302` — 'I cannot, cannot—'

**duplicate_text** (2+ chunks):
  - `1da879b12b` — '(2 copies) πολλαὶ μορφαὶ τῶν δαιμονίων, πολλὰ δ’ ἀέλπτως κραίνουσι θεοί· καὶ τὰ δοκηθέντ’ οὐκ ἐτελέσθη, τῶν δ’ ἀδοκήτων πόρον ηὗρε θεός. τοιόνδ’ ἀπέβη '
  - `7ad49f2871` — '(2 copies) Μή μοι μὴ προσδίδου· μόνος μόνῳ γέμιζε πορθμίδος σκάφος. χαιρέτω μὲν αὖλις ἅδε, χαιρέτω δὲ θυμάτων ἀποβώμιος ἃν ἔχει θυσίαν Κύκλωψ Αἰτναῖος '

### Marcus Aurelius

**tiny_chunk** (29+ chunks):
  - `c3741590c8` — 'Title: Meditations'
  - `1ae866fb8a` — 'Language: English'
  - `359097d8db` — 'By Marcus Aurelius'
  - `44ad1146a8` — 'concerning HIMSELF:'
  - `6908a4ea33` — 'hath not.'

**mostly_digits** (6+ chunks):
  - `ce886327c2` — '[11] iii. 21.'
  - `650401ea02` — '[18] Ad M. Caes ii. 10,; iii. 18,; ii. 4.'
  - `756148a683` — '[22] Ad M. Caes., v. 27,; V. 22.'
  - `62c294fda1` — '[31] ii. 14'
  - `dd3991a237` — '[32] iv. 5,6.'

**long_s_misread** (3+ chunks):
  - `b3550e9c32` — 'It is instructive to compare the _Meditations_ with another famous book, the _Imitation of Christ_. There is the same ideal of self-control in both. It should b'
  - `7ee7a26660` — 'But there is one great difference between the two books we are considering. The _Imitation_ is addressed to others, the _Meditations_ by the writer to himself. '
  - `e91614239b` — 'LIV. The sun seemeth to be shed abroad. And indeed it is diffused but not effused. For that diffusion of it is a τάσις or an extension. For therefore are the be'

**glyph_soup** (1+ chunks):
  - `650401ea02` — '[18] Ad M. Caes ii. 10,; iii. 18,; ii. 4.'

### Homer

**long_s_misread** (35+ chunks):
  - `35f7463968` — "Then took he two sons of Priam, Dardanus' son, Echemmon and Chromius, the twain being in one car. Even as a lion leapeth among the kine and breaketh the neck of"
  - `6e40656e13` — 'So saying they mounted upon the inlaid car and eagerly drave the swift horses against the son of Tydeus. And Sthenelus, the glorious son of Capaneus, saw them a'
  - `09a2baa97f` — 'So spake she, and Ares gave her his horses with frontlets of gold; and she mounted upon the car, her heart distraught, and beside her mounted Iris and took the '
  - `63971973fe` — 'Even as a black darkness appeareth from the clouds when after heat a blustering wind ariseth, even in such wise unto Diomedes, son of Tydeus, did brazen Ares ap'
  - `ced64a9480` — 'My father verily goodly Achilles slew, for utterly laid he waste the well-peopled city of the Cilicians, even Thebe of lofty gates. He slew Eëtion, yet he despo'

### New Testament

**duplicate_text** (13+ chunks):
  - `e20d5dd514` — '(5 copies) χάρις ὑμῖν καὶ εἰρήνη ἀπὸ θεοῦ πατρὸς ἡμῶν καὶ κυρίου Ἰησοῦ Χριστοῦ.'
  - `23747a1aae` — '(2 copies) ἕως ἂν θῶ τοὺς ἐχθρούς σου ὑποπόδιον τῶν ποδῶν σου.'
  - `165c734f32` — '(2 copies) ἐπαχύνθη γὰρ ἡ καρδία τοῦ λαοῦ τούτου, καὶ τοῖς ὠσὶν βαρέως ἤκουσαν, καὶ τοὺς ὀφθαλμοὺς αὐτῶν ἐκάμμυσαν· μήποτε ἴδωσιν τοῖς ὀφθαλμοῖς καὶ το'
  - `d61508d2e7` — '(2 copies) καὶ μακάριός ἐστιν ὃς ἐὰν μὴ σκανδαλισθῇ ἐν ἐμοί.'
  - `0f4af9e7b4` — '(2 copies) ὁ μὴ ὢν μετʼ ἐμοῦ κατʼ ἐμοῦ ἐστιν, καὶ ὁ μὴ συνάγων μετʼ ἐμοῦ σκορπίζει.'

**tiny_chunk** (6+ chunks):
  - `8c762c87fa` — 'πάντοτε χαίρετε,'
  - `2b1a61eed6` — 'γνωστὰ ἀπʼ αἰῶνος.'
  - `5ba65c6e50` — 'ἐδάκρυσεν ὁ Ἰησοῦς.'
  - `5498d9fdad` — 'καὶ ὁ δεύτερος⸃'
  - `b6c71a50d7` — 'ὁ ἔχων ὦτα ἀκουέτω.'

### Aeschylus

**duplicate_text** (10+ chunks):
  - `ce691dfdd4` — '(2 copies) For surely with a great leap from above I bring down the heavily falling force of my foot, my limbs that trip even swift runners—unendurable'
  - `1866a567f3` — '(2 copies) ἐπὶ δὲ τῷ τεθυμένῳ τόδε μέλος, παρακοπά, παραφορὰ φρενοδαλής, ὕμνος ἐξ Ἐρινύων, δέσμιος φρενῶν, ἀφόρ- μικτος, αὐονὰ βροτοῖς.'
  - `39a163d5cc` — '(2 copies) δωμάτων γὰρ εἱλόμαν ἀνατροπάς, ὅταν Ἄρης τιθασὸς ὢν φίλον ἕλῃ. ἐπὶ τὸν ὧδʼ ἱέμεναι κρατερὸν ὄνθʼ ὅμως ἀμαυ- ροῦμεν ὑφʼ αἵματος νέου.'
  - `6eeeccc9c5` — '(2 copies) μάλα γὰρ οὖν ἁλομένα ἀνέκαθεν βαρυπεσῆ καταφέρω ποδὸς ἀκμάν, σφαλερὰ καὶ τανυδρόμοις κῶλα, δύσφορον ἄταν.'
  - `d73cd0fec3` — '(2 copies) Oh raise a shout of triumph over the escape of our master’s house from its misery and the wasting of its wealth by two who were unclean, its'

**long_s_misread** (6+ chunks):
  - `db81d3abcd` — 'Argos Watchman Release from this weary task of mine has been my plea to the gods throughout this long year’s watch, in which, lying upon the palace roof of the '
  - `017b6782c5` — 'First, in this prayer of mine, I give the place of highest honor among the gods to the first prophet, Earth; and after her to Themis, for she was the second to '
  - `d4faeda5f1` — 'O father, who perished by a death unbefitting a king, grant in answer to my prayer the lordship over your halls! And I too, father, have a like request of you: '
  - `aa95dab51b` — 'To earth’s remotest limit we come, to the Scythian land, an untrodden solitude. And now, Hephaestus, yours is the charge to observe the mandates laid upon you b'
  - `cf831c702d` — 'Unfold the whole story and tell us upon what charge Zeus has caught you and painfully punishes you with such dishonor. Instruct us, unless, indeed, there is som'

### Sophocles

**long_s_misread** (14+ chunks):
  - `fc0c5cb61b` — 'My fellow citizens! First, the gods, after tossing the fate of our city on wild waves, have once more righted it. Second, I have ordered you through my messenge'
  - `4422d99648` — 'I came, my child, mindful of your interests no less than my own. But if what I say is wrong, let your way prevail; for united we will follow you. I am ashamed, '
  - `f56119d609` — 'You run loose again, it seems, since Aegisthus is not here, who used always to keep you at least from coming out to the gates and shaming your family. But now, '
  - `a6ac4ea731` — 'I am pursued by joy, dear sister, and I disregard seemliness in order to come with speed. I bring joyful news to relieve your former troubles and grief. And fro'
  - `eff2a4ac80` — 'Feel sure, daughter of Oedipus, that we pity you and him alike for your misfortune; but dreading the punishment of the gods, we could not say anything beyond wh'

**tiny_chunk** (1+ chunks):
  - `cf9b25d39b` — 'What news, then?'

### Hobbes

**run_on_token** (12+ chunks):
  - `93b73a1819` — 'tndoutriquepartitequalemfcprabeat'
  - `7c03cbc1e3` — 'perfuadebiturpropteraffedtusho'
  - `3d99010f94` — 'tercedsreincivifateconitituenda'
  - `fee7c7552d` — 'exemrionemapcemsecclefiafticis'
  - `5e6bb9c942` — 'tionediligentiffimamotuumLinguae'

### Lucretius

**long_s_misread** (9+ chunks):
  - `a149388694` — "Thus whosoe'er have held the stuff of things To be but fire, and out of fire the sum, And whosoever have constituted air As first beginning of begotten things, "
  - `c3f824b3c8` — 'In these affairs We wish thee also well aware of this: The atoms, as their own weight bears them down Plumb through the void, at scarce determined times, In sca'
  - `e3d3557e5b` — "Well learn from this: mainly, because we see Even 'mongst visible objects many be That send forth bodies, loosely some diffused- Like smoke from oaken logs and "
  - `455dee4f1f` — "And to whate'er pursuit A man most clings absorbed, or what the affairs On which we theretofore have tarried much, And mind hath strained upon the more, we seem"
  - `880e52a1dc` — "ORIGINS OF VEGETABLE AND ANIMAL LIFE And now to what remains!- Since I've resolved By what arrangements all things come to pass Through the blue regions of the "

### Empedocles

**tiny_chunk** (5+ chunks):
  - `320884cf77` — 'Liebe.'
  - `ea5dbc0228` — 'SıupL. phys. 1184,'
  - `e5e6527559` — 'καὶ μετ᾽ ὀλίγα"'
  - `8c1c4cce04` — 'ἡ. Körper).'
  - `ea4ef8d72a` — 'Der Lebens beraubt.'

**glyph_soup** (1+ chunks):
  - `2e62a536f1` — 'Aufl. 17 Aufl. 18 5, , m 2 7 a \\ , DA m ” [4'

**mostly_digits** (1+ chunks):
  - `2e62a536f1` — 'Aufl. 17 Aufl. 18 5, , m 2 7 a \\ , DA m ” [4'

### Origen

**long_s_misread** (7+ chunks):
  - `e5d3c86ac4` — 'And since Celsus, although professing to know all about the Gospel , reproaches the Saviour because of His sufferings, saying that He received no assistance fro'
  - `85eb079f83` — 'Exceedingly weak is his assertion, that the disciples of Jesus wrote such accounts regarding him, by way of extenuating the charges that told against him: as if'
  - `917fae0cc0` — 'Celsus in the next place says, with indescribable silliness: If, after inventing defences which are absurd, and by which you were ridiculously deluded, you imag'
  - `56e76ebfa3` — 'And as a sequel to his non-understanding of the statements regarding the wrath of God , he continues: Is it not ridiculous to suppose that, whereas a man , who '
  - `6a851d5347` — 'And there is no truth in the statement of Celsus, that God does the most shameless deeds , or suffers the most shameless sufferings, or that He favours the comm'

### Rousseau

**long_s_misread** (2+ chunks):
  - `4db1a33529` — 'Le sens de l’odorat est au goût ce que celui de la vue est au toucher : il le prévient, il l’avertit de la maniere dont telle ou telle substance doit l’affecter'
  - `caf4467c6d` — 'Voilà bien des difficultés, mon enfant, & ce n’est pas tout. Parmi tant de religions diverses qui se proscrivent & s’excluent mutuellement, une seule est la bon'

**tiny_chunk** (2+ chunks):
  - `811009f910` — 'PRÉFACE'
  - `97c654ec2d` — 'PREMIÈRE PARTIE'

**duplicate_text** (2+ chunks):
  - `bc57636d1d` — '(4 copies) DU CONTRACT SOCIAL ; OU, PRINCIPES DU DROIT POLITIQUE.'
  - `77302daad5` — '(4 copies) Sommaire | À la République de Genève | Préface | Première partie | Seconde partie | Notes'

### Epictetus

**long_s_misread** (3+ chunks):
  - `3d31ca6948` — 'Wisheth all happiness. I neither composed the Discourses of Epictetus in the sense in which things of this nature can properly be said to have been composed, no'
  - `dd503be43a` — 'There are things which are within our power, and there are things which are beyond our power. Within our power are opinion, aim, desire, aversion, and, in one w'
  - `366fcec624` — 'A life at odds with Fortune resembles a wintry torrent; for it is turbulent and muddy and difficult to pass, and violent and noisy and brief. A soul conversant '

**tiny_chunk** (3+ chunks):
  - `34b24b9f7b` — "— οὐδ' ὁτιοῦν."
  - `20532b720c` — '— ἡδονή.'
  - `651c07f37e` — 'οὔ:'

### Plato

**tiny_chunk** (2+ chunks):
  - `b8107bc975` — 'all its members.'
  - `554f27a7bc` — 'Good-luck be thine!'

**long_s_misread** (1+ chunks):
  - `ec4f0e8f00` — 'from that source than from his own craft; but each several craftsman in the State shall have one single craft, and gain from it his living. This law the city-st'

### Xenophanes

**tiny_chunk** (3+ chunks):
  - `f78109733f` — 'καὶ'
  - `5bdbba2b1c` — 'Kirschbaum.'
  - `2ed67aced0` — 'Frosch.'

### Pascal

**tiny_chunk** (1+ chunks):
  - `cc47f9c08b` — 'MÉMORIAL'

**mostly_digits** (1+ chunks):
  - `8aa1df4aa1` — 'Man. 12988, f. fr. ; fol. 72]\ufeff946 bis'

### Heraclitus

**tiny_chunk** (2+ chunks):
  - `f50d33eded` — '.'
  - `1fd5d44e88` — 'Annäherung.'

### Spinoza

**tiny_chunk** (1+ chunks):
  - `5e55efa6ce` — 'Homo cogitat.'

### Anaxagoras

**tiny_chunk** (1+ chunks):
  - `854fa03c39` — 'Aufl. 26'

### Diogenes of Apollonia

**long_s_misread** (1+ chunks):
  - `96799835eb` — 'Und dieser mit Geisteskraft ausgestattete Urstoff ist meines Bedünkens das, was von den Leuten die Luft genannt wird, und er lenkt alle und beherrscht alle. Den'
