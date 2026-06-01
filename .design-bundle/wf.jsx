/* Concordance wireframes — 6 screens × 2 form factors = 12 frames.
   Greyscale boxes-and-labels. Real German lemmas + KWIC content.
   Callouts annotate non-obvious interactions. */

const { useState } = React;

/* ─── Shared stub chrome (desktop) ─── */
function TopNav({ cur }) {
  const items = ['Read', 'Refs', 'Network', 'Chat', 'Concordance'];
  return (
    <div className="stub-topnav">
      <span className="brand">Π <em>poietes</em></span>
      <div className="nav">
        {items.map((it) => (
          <span key={it} className={cur === it ? 'cur' : ''}>{it}</span>
        ))}
      </div>
      <span className="spacer" />
      <div className="right">
        <div className="box" />
        <div className="box" style={{ width: 24 }} />
      </div>
    </div>
  );
}
function Side() {
  return (
    <div className="stub-side">
      <div className="box" /><div className="box" /><div className="box" />
    </div>
  );
}

/* ─── Mobile bezel ─── */
function MobShell({ title, titleEm, action, back, children }) {
  return (
    <>
      <div className="m-status">
        <span>9:41</span>
        <span className="dots"><span className="dot" /><span className="dot" /><span className="dot" /></span>
      </div>
      <div className="m-topbar">
        {back ? <span className="back">‹ {back}</span> : <span className="ham" />}
        <span className="title">{title} {titleEm && <em>· {titleEm}</em>}</span>
        <span className="action">{action || ''}</span>
      </div>
      <div className="m-body">{children}</div>
      <div className="m-home"><span className="bar" /></div>
    </>
  );
}

/* ───── Scope pill (desktop) ───── */
function ScopePill({ steps, count }) {
  return (
    <span className="scope-pill">
      {steps.map((s, i) => (
        <span key={i} className={`crumb ${s.cur ? 'cur' : ''}`}>
          {i > 0 && !s.cur && <span className="arr">‹</span>}
          {s.label}
        </span>
      ))}
      {count && <span className="ct"><b>{count}</b> occurrences</span>}
    </span>
  );
}

/* ─── A-Z rail ─── */
const AZ = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('');
const AZ_GERMAN = ['A','B','D','E','F','G','H','I','K','L','M','N','O','P','R','S','T','U','V','W','Z'];
function AZRail({ cur, has, klass = 'az-rail' }) {
  return (
    <div className={klass}>
      {AZ.map((L) => {
        const c = L === cur ? 'cur' : has.includes(L) ? 'has' : '';
        return <span key={L} className={`l ${c}`}>{L}</span>;
      })}
    </div>
  );
}

/* ════════════════════════════════════════════════════════════ */
/* F1 DESKTOP — Lemma frequency index                            */
/* ════════════════════════════════════════════════════════════ */

const TOP_LEMMAS = [
  { rk: 1, lem: 'Geist',       pos: 'noun · m.',  ct: '1,247', gloss: 'spirit · mind',         spark: [3,5,7,9,11,8,6,9,12,10,8,6,4,5] },
  { rk: 2, lem: 'Wesen',       pos: 'noun · n.',  ct: '892',   gloss: 'essence · being',       spark: [2,4,6,5,7,9,11,9,7,6,5,4,3,5] },
  { rk: 3, lem: 'Begriff',     pos: 'noun · m.',  ct: '804',   gloss: 'concept · notion',      spark: [4,6,7,8,7,9,8,7,9,11,8,6,5,4] },
  { rk: 4, lem: 'Bewußtsein',  pos: 'noun · n.',  ct: '612',   gloss: 'consciousness',         spark: [3,5,8,10,12,11,9,7,6,5,4,3,2,2] },
  { rk: 5, lem: 'Erkenntnis',  pos: 'noun · f.',  ct: '445',   gloss: 'knowledge · cognition', spark: [2,3,4,5,6,7,8,7,6,5,4,3,2,2] },
];
const A_LEMMAS = [
  { rk: 6, lem: 'Aufhebung',   pos: 'noun · f.',  ct: '231',   gloss: 'sublation · cancellation', spark: [1,2,3,4,5,6,7,6,5,4,3,2,1,1] },
  { rk: 7, lem: 'Anschauung',  pos: 'noun · f.',  ct: '198',   gloss: 'intuition',             spark: [1,2,3,3,4,5,5,4,3,3,2,2,1,1] },
];

function Sparkline({ data }) {
  const max = Math.max(...data);
  return (
    <div className="spark">
      {data.map((v, i) => (
        <span key={i} className="bar" style={{ height: `${(v / max) * 100}%` }} />
      ))}
    </div>
  );
}

function LbRow({ row }) {
  return (
    <div className="lb-row">
      <span className="rk">{row.rk}</span>
      <span className="lem">{row.lem}</span>
      <span className="pos">{row.pos}</span>
      <span className="ct">{row.ct}</span>
      <Sparkline data={row.spark} />
      <span className="gloss">{row.gloss}</span>
    </div>
  );
}

function F1Desktop({ dark }) {
  return (
    <div className={`wf${dark ? ' dark' : ''}`}>
      <TopNav cur="Concordance" />
      <Side />

      <div className="conc-head">
        <div className="h-row">
          <div>
            <div className="h1">Concordance</div>
            <div style={{ marginTop: 14, display: 'flex', alignItems: 'center', gap: 14 }}>
              <ScopePill
                steps={[
                  { label: 'Work' },
                  { label: 'Author' },
                  { label: 'Corpus · All German', cur: true },
                ]}
                count="14,892"
              />
              <span className="h-meta" style={{ marginLeft: 4 }}>· <b>2,148</b> lemmas · DEU</span>
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <span className="search-stub"><span className="ico">⌕</span>Find lemma — type any German word…</span>
            <div className="h-meta" style={{ marginTop: 10 }}>SORT <b>BY FREQUENCY</b> · A→Z · BY POS</div>
          </div>
        </div>
      </div>

      <AZRail cur="A" has={AZ_GERMAN} />

      <div className="leaderboard">
        <div className="lb-letter">A</div>
        {A_LEMMAS.map((r) => <LbRow key={r.lem} row={r} />)}
        <div className="lb-letter">B–E</div>
        {TOP_LEMMAS.slice(2, 5).map((r) => <LbRow key={r.lem} row={r} />)}
        <div className="lb-letter">G</div>
        <LbRow row={TOP_LEMMAS[0]} />
        <div className="lb-letter">W</div>
        <LbRow row={TOP_LEMMAS[1]} />
      </div>

      <div className="callout t-down" style={{ top: 184, left: 540 }}>
        <span className="num">1</span>
        Scope pill is always visible. <b>Corpus</b> is the default at the
        top-nav entry point — no work needed.
      </div>
      <div className="callout t-up" style={{ top: 184, right: 240 }}>
        <span className="num">2</span>
        Search jumps to a lemma directly · A–Z rail jumps to the letter section.
      </div>
      <div className="callout t-right" style={{ top: 330, left: 1280 }}>
        <span className="num">3</span>
        Inactive letters faded · current letter inverted.
      </div>
      <div className="callout t-left" style={{ top: 450, right: 230 }}>
        <span className="num">4</span>
        Sparkline = frequency by work (Phänomenologie · Wissenschaft · Logik ·
        Recht · etc). Hover reveals work names.
      </div>

      <div className="frame-foot">F1 · Lemma frequency index · desktop 1440×900 · corpus scope</div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════════ */
/* F1 MOBILE                                                     */
/* ════════════════════════════════════════════════════════════ */

function F1Mobile({ dark }) {
  return (
    <div className={`wf mob${dark ? ' dark' : ''}`}>
      <MobShell title="Concordance" action="⌕">
        <div className="m-chips">
          <span className="m-chip">Work</span>
          <span className="m-chip">Author</span>
          <span className="m-chip on">Corpus · DEU <span className="ct">14,892</span></span>
          <span className="m-chip">By POS</span>
          <span className="m-chip">Sort ▾</span>
        </div>

        <div className="m-az">
          {AZ.map((L) => {
            const c = L === 'A' ? 'cur' : AZ_GERMAN.includes(L) ? 'has' : '';
            return <span key={L} className={`l ${c}`}>{L}</span>;
          })}
        </div>

        <div className="m-lb-letter">A</div>
        {A_LEMMAS.map((r) => (
          <div key={r.lem} className="m-lb-row">
            <span className="rk">{r.rk}</span>
            <span>
              <span className="lem">{r.lem}</span>
              <span className="pos">{r.pos} · {r.gloss}</span>
            </span>
            <span className="ct">{r.ct}</span>
          </div>
        ))}
        <div className="m-lb-letter">G</div>
        <div className="m-lb-row">
          <span className="rk">1</span>
          <span>
            <span className="lem">Geist</span>
            <span className="pos">noun · masc · spirit · mind</span>
          </span>
          <span className="ct">1,247</span>
        </div>
        <div className="m-lb-letter">W</div>
        <div className="m-lb-row">
          <span className="rk">2</span>
          <span>
            <span className="lem">Wesen</span>
            <span className="pos">noun · neut · essence</span>
          </span>
          <span className="ct">892</span>
        </div>
      </MobShell>

      <div className="callout t-up" style={{ top: 96, left: 110 }}>
        <span className="num">1</span>
        Rails ⇒ horizontal chip strip. Scope chip carries the count badge.
      </div>
      <div className="callout t-left" style={{ top: 130, right: 28 }}>
        <span className="num">2</span>
        A–Z rail clings to right edge · 9pt letters · tap drops a tooltip.
      </div>
      <div className="callout t-right" style={{ top: 360, left: 350 }}>
        <span className="num">3</span>
        Sparkline removed at mobile scale — gloss moved into POS line.
      </div>

      <div className="frame-foot">F1 · mobile 390×844</div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════════ */
/* F2 DESKTOP — Lemma detail / KWIC grid                         */
/* ════════════════════════════════════════════════════════════ */

const KWIC_ROWS = [
  { loc: ['PhdG', 'Vorrede', '¶12'],   left: 'wird die Natur in ihrer Tiefe nur von dem',           m: 'Geiste', right: 'erfaßt, der sich selbst erkennt und das Sein als',          morph: 'Dat · Sg', surf: 'Geiste' },
  { loc: ['PhdG', 'Vorrede', '¶17'],   left: 'das Wahre nur als wissenschaftliches System ist; daß die Substanz wesentlich', m: 'Geist', right: 'sei, drückt diejenige Vorstellung aus, welche das', morph: 'Nom · Sg', surf: 'Geist' },
  { loc: ['PhdG', 'B · IV', '¶178'],   left: 'erfahren, was er ist — nämlich daß er sich als',     m: 'Geist',  right: 'erfasse. Was hierin der Reichtum des Wissens',               morph: 'Akk · Sg', surf: 'Geist' },
  { loc: ['PhdG', 'C · V', '¶235'],    left: 'des Bewußtseins, das die Welt durchdringt — der',     m: 'Geist',  right: 'ist gewiß, sich selber alle Realität zu sein.',              morph: 'Nom · Sg', surf: 'Geist' },
  { loc: ['PhdG', 'C · VI', '¶441'],   left: 'allgemeine Substanz spricht; das absolute Wesen, der', m: 'Geist',  right: 'der die einzelnen Wirklichkeiten in sich aufgehoben hat',     morph: 'Nom · Sg', surf: 'Geist' },
  { loc: ['PhdG', 'C · VI', '¶463'],   left: 'die sittliche Welt — diese Welt ist der',             m: 'Geist',  right: 'der seine Wahrheit unmittelbar an seinem Dasein hat;',        morph: 'Nom · Sg', surf: 'Geist' },
  { loc: ['PhdG', 'C · VII', '¶672'],  left: 'so daß die Religion das Bewußtsein des absoluten',    m: 'Geistes', right: 'überhaupt ist. — Aber dieses Bewußtsein des absoluten',     morph: 'Gen · Sg', surf: 'Geistes' },
  { loc: ['PhdG', 'C · VIII', '¶788'], left: 'allein die Bewegung, in welcher der erscheinende',     m: 'Geist',  right: 'sich selbst zur Substanz aufbaut. — Die Vollendung',         morph: 'Nom · Sg', surf: 'Geist' },
];

function FilterRail() {
  return (
    <div className="filter-rail">
      <div className="fr-group">
        <div className="fr-label"><span>Work</span><span className="clr">clear</span></div>
        <div className="fr-check on"><span className="box" /><span>Phänomenologie</span><span className="ct">312</span></div>
        <div className="fr-check"><span className="box" /><span>Wiss. der Logik</span><span className="ct">418</span></div>
        <div className="fr-check"><span className="box" /><span>Rechtsphilosophie</span><span className="ct">204</span></div>
        <div className="fr-check"><span className="box" /><span>Enzyklopädie</span><span className="ct">313</span></div>
      </div>

      <div className="fr-group">
        <div className="fr-label"><span>Case</span></div>
        <div className="fr-opts">
          <span className="fr-opt on">Nom</span>
          <span className="fr-opt">Akk</span>
          <span className="fr-opt">Gen</span>
          <span className="fr-opt">Dat</span>
        </div>
      </div>

      <div className="fr-group">
        <div className="fr-label"><span>Number</span></div>
        <div className="fr-opts">
          <span className="fr-opt">Sg</span>
          <span className="fr-opt">Pl</span>
        </div>
      </div>

      <div className="fr-group">
        <div className="fr-label"><span>Gender</span></div>
        <div className="fr-opts">
          <span className="fr-opt muted">Mask</span>
          <span className="fr-opt muted">Fem</span>
          <span className="fr-opt muted">Neut</span>
        </div>
        <div style={{ marginTop: 6, fontFamily: 'var(--wf-sans)', fontSize: 10, color: 'var(--wf-ink-3)' }}>
          locked — Geist is masc.
        </div>
      </div>

      <div className="fr-group">
        <div className="fr-label"><span>Surface form</span></div>
        <div className="fr-opts">
          <span className="fr-opt on">Geist</span>
          <span className="fr-opt">Geistes</span>
          <span className="fr-opt">Geiste</span>
          <span className="fr-opt">Geister</span>
        </div>
      </div>
    </div>
  );
}

function KwicRow({ row, cur }) {
  return (
    <div className={`kwic-row ${cur ? 'cur' : ''}`}>
      <span className="loc"><b>{row.loc[0]}</b><br/>{row.loc[1]} · {row.loc[2]}</span>
      <span className="left">{row.left}</span>
      <span className="match">{row.m}</span>
      <span className="right">{row.right}</span>
      <span className="meta">
        <span className="surf">{row.surf}</span>
        <span>{row.morph}</span>
      </span>
    </div>
  );
}

function F2Desktop({ dark }) {
  return (
    <div className={`wf${dark ? ' dark' : ''}`}>
      <TopNav cur="Concordance" />
      <Side />

      <div className="conc-head">
        <div className="h-row">
          <div>
            <span style={{ fontFamily: 'var(--wf-serif)', fontStyle: 'italic', fontSize: 32, color: 'var(--wf-ink)' }}>Geist</span>
            <span style={{ marginLeft: 14, fontFamily: 'var(--wf-sans)', fontSize: 11, color: 'var(--wf-ink-3)', letterSpacing: '0.08em' }}>
              NOUN · MASC · DEU · LEMMA · <b style={{ color: 'var(--wf-ink)' }}>1,247</b> OCCURRENCES
            </span>
            <div style={{ marginTop: 12 }}>
              <ScopePill steps={[
                { label: 'Corpus' },
                { label: 'Hegel' },
                { label: 'Phänomenologie des Geistes', cur: true },
              ]} count="312" />
              <span style={{ marginLeft: 12, fontFamily: 'var(--wf-sans)', fontSize: 10, color: 'var(--wf-callout)', letterSpacing: '0.04em' }}>
                ‹ zoom out to Hegel (all works) · ‹‹ zoom out to corpus
              </span>
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontFamily: 'var(--wf-serif)', fontStyle: 'italic', fontSize: 14, color: 'var(--wf-ink-2)', maxWidth: 340 }}>
              <span style={{ fontWeight: 600, color: 'var(--wf-ink)' }}>spirit · mind</span> — Hegel's term for the
              self-knowing universal that constitutes the proper subject of philosophy.
            </div>
          </div>
        </div>
      </div>

      <div className="kwic-stage">
        <FilterRail />
        <div className="kwic-pane">
          <div className="kwic-toolbar">
            <span className="ct">Showing <b>8</b> of <b>312</b></span>
            <span className="sort">sort: locator <span className="chev">▾</span></span>
            <span className="sort">left-collocate <span className="chev">▾</span></span>
            <span className="sort">right-collocate <span className="chev">▾</span></span>
            <span className="sort">surface form <span className="chev">▾</span></span>
            <span className="spacer" />
            <span className="kbd"><kbd>j</kbd> / <kbd>k</kbd> next / prev · <kbd>↵</kbd> open chunk · <kbd>esc</kbd> back</span>
          </div>
          <div className="kwic-grid">
            {KWIC_ROWS.slice(0,8).map((r, i) => <KwicRow key={i} row={r} cur={i === 2} />)}
          </div>
        </div>
      </div>

      <div className="callout t-right" style={{ top: 250, left: 280 }}>
        <span className="num">1</span>
        Morphology filters come from spaCy <code>feats</code>. Gender locks
        when the lemma's gender is fixed (Geist = masc.).
      </div>
      <div className="callout t-up" style={{ top: 215, left: 700 }}>
        <span className="num">2</span>
        Scope pill is the persistent breadcrumb. Tap any segment to zoom
        out one level. See F5.
      </div>
      <div className="callout t-up" style={{ top: 325, right: 240 }}>
        <span className="num">3</span>
        KWIC: centered match (italic serif + oxblood) with the two contexts
        right- and left-fading. <b>The match-column is the heart.</b>
      </div>
      <div className="callout t-left" style={{ top: 250, right: 28 }}>
        <span className="num">4</span>
        Surface form + morphology bound to the right edge — scannable
        without breaking the KWIC alignment.
      </div>
      <div className="callout t-down" style={{ top: 304, left: 1090 }}>
        <span className="num">5</span>
        j / k traverse rows · ↵ opens <code>/api/chunks/:id</code> in
        the reader · esc returns.
      </div>

      <div className="frame-foot">F2 · KWIC grid · desktop · scope = Hegel · Phänomenologie</div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════════ */
/* F2 MOBILE                                                     */
/* ════════════════════════════════════════════════════════════ */

function F2Mobile({ dark }) {
  return (
    <div className={`wf mob${dark ? ' dark' : ''}`}>
      <MobShell title="Geist" titleEm="312" back="Concordance" action="⚒">
        <div className="m-scope">
          <span className="crumb">Corpus</span>
          <span className="arr">›</span>
          <span className="crumb">Hegel</span>
          <span className="arr">›</span>
          <span className="crumb cur">PhdG</span>
          <span className="right"><b>312</b> hits</span>
        </div>
        <div className="m-chips">
          <span className="m-chip on">Nom</span>
          <span className="m-chip">Akk</span>
          <span className="m-chip">Gen</span>
          <span className="m-chip">Dat</span>
          <span className="m-chip">Sg</span>
          <span className="m-chip">Pl</span>
          <span className="m-chip">Geist <span className="ct">208</span></span>
        </div>
        {KWIC_ROWS.slice(0, 5).map((r, i) => (
          <div key={i} className="m-kwic-row">
            <div className="top">
              <span className="match">{r.m}</span>
              <span className="loc">{r.loc[0]} · <b>{r.loc[1]}</b> · {r.loc[2]}</span>
            </div>
            <div className="ctx">… {r.left} <span className="strike">{r.m}</span> {r.right} …</div>
            <div className="morph"><span className="surf">{r.surf}</span>{r.morph}</div>
          </div>
        ))}
      </MobShell>

      <div className="callout t-down" style={{ top: 100, left: 24 }}>
        <span className="num">1</span>
        Scope = breadcrumb row · count anchored right.
      </div>
      <div className="callout t-right" style={{ top: 140, left: 280 }}>
        <span className="num">2</span>
        Filters ⇒ horizontal chip strip · sort lives in ⚒ sheet (top-right).
      </div>
      <div className="callout t-up" style={{ top: 270, left: 290 }}>
        <span className="num">3</span>
        Stacked KWIC: <b>match + locator on top</b>, full sentence below
        with the match marked inline. Touch target = entire row, 56pt+.
      </div>

      <div className="frame-foot">F2 · KWIC · mobile · stacked layout</div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════════ */
/* F3 DESKTOP — Reader sidebar Concordance tab                   */
/* ════════════════════════════════════════════════════════════ */

const SIDEBAR_LEMMAS = [
  { lem: 'Geist',       pos: 'noun · m.', here: 12, work: 312, cur: true },
  { lem: 'Wesen',       pos: 'noun · n.', here: 8,  work: 178 },
  { lem: 'Bewußtsein',  pos: 'noun · n.', here: 7,  work: 244 },
  { lem: 'Begriff',     pos: 'noun · m.', here: 6,  work: 156 },
  { lem: 'erfassen',    pos: 'verb',      here: 4,  work: 87 },
  { lem: 'Substanz',    pos: 'noun · f.', here: 3,  work: 64 },
  { lem: 'Wahrheit',    pos: 'noun · f.', here: 3,  work: 109 },
  { lem: 'absolut',     pos: 'adj.',      here: 3,  work: 91 },
];

function F3Desktop({ dark }) {
  return (
    <div className={`wf${dark ? ' dark' : ''}`}>
      <TopNav cur="Read" />
      <Side />

      <div className="reader-sb-stage">
        <div className="reader-col">
          <div className="col-label">Hegel · Phänomenologie des Geistes · Vorrede ¶17</div>
          <p className="para">
            Es kommt nach meiner Einsicht … alles darauf an, das Wahre nicht als{' '}
            <span className="term">Substanz</span>, sondern <em>ebensosehr als</em>{' '}
            <span className="term cur">Subjekt</span> aufzufassen. Zugleich ist zu bemerken, daß die Substantialität
            so sehr das Allgemeine oder die <span className="term">Unmittelbarkeit</span> des Wissens selbst,
            als diejenige, welche Sein oder Unmittelbarkeit für das Wissen ist, in sich schließt.
          </p>
          <p className="para">
            Daß das Wahre nur als System wirklich, oder daß die Substanz wesentlich{' '}
            <span className="term cur">Geist</span> sei, drückt diejenige Vorstellung aus,
            welche das <span className="term">Absolute</span> als Geist ausspricht, — der erhabenste{' '}
            <span className="term">Begriff</span>, und der der neueren Zeit und ihrer Religion angehört.
          </p>
          <p className="para">
            Das Geistige allein ist das <span className="term">Wirkliche</span>; es ist das{' '}
            <span className="term cur">Wesen</span> oder Ansichseiende — das sich Verhaltende und{' '}
            <span className="term">Bestimmte</span>, das Anderssein und Für-sich-sein — und in dieser
            Bestimmtheit oder seinem Außersichsein in sich selbst Bleibende; — oder es ist an und für sich.
          </p>
        </div>

        <div className="sb-panel">
          <div className="sb-tabs">
            <span className="sb-tab">Word</span>
            <span className="sb-tab">Notes</span>
            <span className="sb-tab cur">Concordance</span>
          </div>
          <div className="sb-body">
            <div className="sb-scope">
              <ScopePill steps={[
                { label: 'In this work', cur: true },
                { label: 'Hegel' },
                { label: 'Corpus' },
              ]} />
            </div>
            <div className="sb-title">Lemmas in Vorrede ¶17 · sorted by freq.</div>
            {SIDEBAR_LEMMAS.map((l) => (
              <div key={l.lem} className={`sb-lemma ${l.cur ? 'cur' : ''}`}>
                <span>
                  <span className="lem">{l.lem}</span>
                  <span className="pos">{l.pos}</span>
                </span>
                <span className="ct">
                  {l.here}<span className="work">{l.work} in work</span>
                </span>
                <span className="arr">›</span>
              </div>
            ))}
            <div className="sb-foot">
              <span>See all in this work →</span>
              <span style={{ color: 'var(--wf-ink-3)' }}>open full KWIC</span>
            </div>
          </div>
        </div>
      </div>

      <div className="callout t-down" style={{ top: 70, left: 980 }}>
        <span className="num">1</span>
        Concordance becomes a third tab next to <b>Word</b> and <b>Notes</b>.
      </div>
      <div className="callout t-left" style={{ top: 195, right: 30 }}>
        <span className="num">2</span>
        In-work scope by default — the lemmas that appear in <em>this</em>{' '}
        passage, sorted by local frequency. Each row carries both
        <em>here</em> and <em>work-wide</em> counts.
      </div>
      <div className="callout t-right" style={{ top: 340, left: 850 }}>
        <span className="num">3</span>
        Active lemma in the body text reflects the highlighted row (oxblood
        underline). Hovering a row hi-lites the same word in the reader.
      </div>
      <div className="callout t-up" style={{ top: 800, left: 1100 }}>
        <span className="num">4</span>
        Footer link opens full KWIC at <b>work</b> scope.
      </div>

      <div className="frame-foot">F3 · Reader sidebar · Concordance tab · in-work scope</div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════════ */
/* F3 MOBILE                                                     */
/* ════════════════════════════════════════════════════════════ */

function F3Mobile({ dark }) {
  return (
    <div className={`wf mob${dark ? ' dark' : ''}`}>
      <MobShell title="Hegel" titleEm="PhdG · ¶17" action="Aa">
        {/* dimmed reader behind drawer */}
        <div style={{ padding: 16, opacity: 0.35, pointerEvents: 'none' }}>
          <p style={{ fontFamily: 'var(--wf-serif)', fontSize: 13, lineHeight: 1.6, color: 'var(--wf-ink-2)' }}>
            Es kommt nach meiner Einsicht alles darauf an, das Wahre nicht als
            Substanz, sondern ebensosehr als Subjekt aufzufassen…
          </p>
        </div>

        <div className="m-drawer">
          <div className="d-head">
            <span className="ttl">Concordance</span>
            <span className="x">×</span>
          </div>
          <div className="d-tabs">
            <span className="d-tab">Word</span>
            <span className="d-tab">Notes</span>
            <span className="d-tab cur">Concord</span>
          </div>
          <div className="m-scope" style={{ borderBottom: '1px solid var(--wf-line-4)' }}>
            <span className="crumb cur">In this work</span>
            <span className="arr">›</span>
            <span className="crumb">Hegel</span>
            <span className="arr">›</span>
            <span className="crumb">Corpus</span>
          </div>
          {SIDEBAR_LEMMAS.slice(0, 6).map((l) => (
            <div key={l.lem} className={`sb-lemma ${l.cur ? 'cur' : ''}`} style={{ margin: '0 14px', padding: '10px 0' }}>
              <span>
                <span className="lem">{l.lem}</span>
                <span className="pos">{l.pos}</span>
              </span>
              <span className="ct">
                {l.here}<span className="work">{l.work} work</span>
              </span>
              <span className="arr">›</span>
            </div>
          ))}
          <div style={{ marginTop: 'auto', padding: '12px 18px', borderTop: '1px solid var(--wf-line-3)',
                       fontFamily: 'var(--wf-sans)', fontSize: 12, color: 'var(--wf-callout)' }}>
            See all in this work →
          </div>
        </div>
      </MobShell>

      <div className="callout t-down" style={{ top: 80, left: 30 }}>
        <span className="num">1</span>
        Sidebar ⇒ left-edge drawer · scrim dims the reader.
      </div>
      <div className="callout t-up" style={{ top: 150, left: 250 }}>
        <span className="num">2</span>
        Tab strip stays — Concordance is the third (truncated to "Concord"
        if needed). Tap to close = swipe-out or × in header.
      </div>
      <div className="callout t-left" style={{ top: 470, right: 30 }}>
        <span className="num">3</span>
        Each row is a 44pt+ tap target. Tap = open full KWIC; long-press =
        peek at first 3 occurrences.
      </div>

      <div className="frame-foot">F3 · drawer · 86% width · scrim 0.18</div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════════ */
/* F4 DESKTOP — TermCard with "See all" CTA hover                */
/* ════════════════════════════════════════════════════════════ */

function F4Desktop({ dark }) {
  return (
    <div className={`wf${dark ? ' dark' : ''}`}>
      <TopNav cur="Read" />
      <Side />

      <div className="reader-stage-4">
        <div style={{ fontFamily: 'var(--wf-sans)', fontSize: 10, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--wf-ink-3)', marginBottom: 14 }}>
          Hegel · Phänomenologie des Geistes · Vorrede
        </div>
        <p className="para">
          Daß das Wahre nur als wissenschaftliches System wirklich, oder daß die{' '}
          <span className="term">Substanz</span> wesentlich{' '}
          <span className="term active">Geist</span> sei, drückt diejenige Vorstellung aus, welche das{' '}
          <span className="term">Absolute</span> als Geist ausspricht — der{' '}
          erhabenste Begriff, und der der neueren Zeit und ihrer Religion angehört.
        </p>
        <p className="para">
          Das Geistige allein ist das Wirkliche; es ist das Wesen oder Ansichseiende — das sich
          Verhaltende und Bestimmte, das Anderssein und Für-sich-sein — und in dieser
          Bestimmtheit oder seinem Außersichsein in sich selbst Bleibende; — oder es ist an
          und für sich.
        </p>

        {/* term-card popover */}
        <div className="tcard" style={{ top: 130, left: 460 }}>
          <div className="arrow" style={{ top: -8, left: 36 }} />
          <div className="tcard-head">
            <div className="lem">Geist</div>
            <div className="trans">noun · masculine · DEU · lemma</div>
            <div className="gloss">spirit · mind · the universal self-knowing subject</div>
          </div>
          <div className="tcard-sec">
            <div className="lbl">Renderings · across translations</div>
            <div style={{ display: 'grid', gridTemplateColumns: '80px 1fr', rowGap: 4, fontSize: 12 }}>
              <span style={{ fontFamily: 'var(--wf-sans)', fontSize: 11, color: 'var(--wf-ink-2)' }}>Miller</span>
              <span>Spirit</span>
              <span style={{ fontFamily: 'var(--wf-sans)', fontSize: 11, color: 'var(--wf-ink-2)' }}>Pinkard</span>
              <span>spirit</span>
              <span style={{ fontFamily: 'var(--wf-sans)', fontSize: 11, color: 'var(--wf-ink-2)' }}>Baillie</span>
              <span>Mind</span>
            </div>
          </div>
          <div className="tcard-sec">
            <div className="lbl">Morphology</div>
            <div style={{ fontFamily: 'var(--wf-sans)', fontSize: 12 }}>
              Nom · Sg · Mask · surface = <span style={{ fontFamily: 'var(--wf-serif)', fontStyle: 'italic' }}>Geist</span>
            </div>
          </div>
          <div className="tcard-cta">
            <div className="btn hover">
              <span className="lbl-l">See all 1,247 occurrences</span>
              <span className="arr">→</span>
            </div>
          </div>
        </div>

        {/* hover-preview tip */}
        <div className="cta-tip" style={{ top: 348, left: 840 }}>
          <div style={{ fontFamily: 'var(--wf-sans)', fontSize: 9.5, letterSpacing: '0.14em', color: 'var(--wf-ink-3)', textTransform: 'uppercase', marginBottom: 6 }}>
            Concordance · scope
          </div>
          <div className="row cur"><span className="k">In Phänomenologie</span><span className="v">312</span></div>
          <div className="row"><span className="k">In Hegel · all works</span><span className="v">897</span></div>
          <div className="row"><span className="k">In corpus · DEU</span><span className="v">1,247</span></div>
          <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px dashed var(--wf-line-3)',
                       fontFamily: 'var(--wf-sans)', fontSize: 10, color: 'var(--wf-ink-2)' }}>
            Opens at <b style={{ color: 'var(--wf-ink)' }}>work</b> scope.
            ⌥-click for corpus.
          </div>
        </div>
      </div>

      <div className="callout t-up" style={{ top: 130, left: 720 }}>
        <span className="num">1</span>
        Hover state for the <b>See all</b> CTA: inverts to ink fill +
        paper text. Tap target = full row, 44pt min.
      </div>
      <div className="callout t-up" style={{ top: 330, right: 230 }}>
        <span className="num">2</span>
        On hover, an inline tip surfaces the three scopes ahead of the
        click — sets expectations about how big the list is.
      </div>
      <div className="callout t-left" style={{ top: 470, right: 30 }}>
        <span className="num">3</span>
        Click = open KWIC at <b>work</b> scope (the narrowest useful
        starting point). ⌥-click = corpus.
      </div>
      <div className="callout t-down" style={{ top: 195, left: 540 }}>
        <span className="num">4</span>
        Anchored term carries the active state — fill + solid underline.
        Mirrors the existing TermCard pattern, no new chrome.
      </div>

      <div className="frame-foot">F4 · TermCard · See-all CTA · hover state</div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════════ */
/* F4 MOBILE                                                     */
/* ════════════════════════════════════════════════════════════ */

function F4Mobile({ dark }) {
  return (
    <div className={`wf mob${dark ? ' dark' : ''}`}>
      <MobShell title="Hegel" titleEm="PhdG · Vorrede" action="Aa">
        <div style={{ padding: '14px 18px 0' }}>
          <p style={{ fontFamily: 'var(--wf-serif)', fontSize: 14, lineHeight: 1.6, color: 'var(--wf-ink)' }}>
            Daß die Substanz wesentlich{' '}
            <span style={{ background: 'var(--wf-fill-3)', borderBottom: '1px solid var(--wf-line)' }}>Geist</span>{' '}
            sei, drückt diejenige Vorstellung aus, welche das Absolute als Geist ausspricht — der erhabenste Begriff…
          </p>
        </div>

        <div className="m-tcard">
          <div className="grab"><span className="bar" /></div>
          <div className="h">
            <div className="lem">Geist</div>
            <div className="trans">noun · masc · DEU</div>
            <div className="gloss">spirit · mind</div>
          </div>
          <div className="sec">
            <div className="lbl">Morphology</div>
            <div style={{ fontFamily: 'var(--wf-sans)', fontSize: 12 }}>Nom · Sg · Mask</div>
          </div>
          <div className="sec">
            <div className="lbl">Renderings</div>
            <div style={{ fontSize: 12.5 }}>
              <span style={{ fontFamily: 'var(--wf-sans)', fontSize: 10.5, color: 'var(--wf-ink-2)' }}>Miller </span>Spirit{' · '}
              <span style={{ fontFamily: 'var(--wf-sans)', fontSize: 10.5, color: 'var(--wf-ink-2)' }}>Pinkard </span>spirit{' · '}
              <span style={{ fontFamily: 'var(--wf-sans)', fontSize: 10.5, color: 'var(--wf-ink-2)' }}>Baillie </span>Mind
            </div>
          </div>
          <div className="cta hover">
            <span>See all <b>1,247</b> occurrences</span>
            <span className="arr">→</span>
          </div>
        </div>
      </MobShell>

      <div className="callout t-up" style={{ top: 460, left: 24 }}>
        <span className="num">1</span>
        Sheet expands from bottom · grab handle for drag-dismiss.
      </div>
      <div className="callout t-right" style={{ top: 720, left: 350 }}>
        <span className="num">2</span>
        CTA = full-width, pressed (inverted) state shown. 48pt min
        height. Tap = push KWIC at work scope.
      </div>
      <div className="callout t-left" style={{ top: 600, right: 30 }}>
        <span className="num">3</span>
        Scope-preview tip drops here on long-press (mirrors desktop
        hover) — overlay above CTA.
      </div>

      <div className="frame-foot">F4 · TermCard sheet · CTA pressed</div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════════ */
/* F5 DESKTOP — Scope-zoom transition                            */
/* ════════════════════════════════════════════════════════════ */

const ZOOM_ROWS_WORK = [
  { l: 'die sittliche Welt — diese Welt ist der', m: 'Geist', r: 'der seine Wahrheit unmittelbar' },
  { l: 'so daß die Religion das Bewußtsein des absoluten', m: 'Geistes', r: 'überhaupt ist' },
  { l: 'allein die Bewegung, in welcher der erscheinende', m: 'Geist', r: 'sich selbst zur Substanz' },
];
const ZOOM_ROWS_AUTHOR = [
  { l: 'die sittliche Welt — diese Welt ist der', m: 'Geist', r: 'der seine Wahrheit unmittelbar' },
  { l: 'Das logische System ist das Reich der Schatten · der', m: 'Geist', r: 'als befreit von aller Sinnlichkeit' },
  { l: 'Das Recht ist als das Dasein des freien Willens · der', m: 'Geist', r: 'als die zweite Natur des Menschen' },
];
const ZOOM_ROWS_CORPUS = [
  { l: 'die sittliche Welt — diese Welt ist der', m: 'Geist', r: 'der seine Wahrheit unmittelbar' },
  { l: 'Kant: der reine Verstand … der menschliche', m: 'Geist', r: 'als Quelle der Synthesis a priori' },
  { l: 'Nietzsche: Sklavenmoral und Herdentier sind dem freien', m: 'Geiste', r: 'das gefährlichste Gift' },
];

function ZoomFrame({ step, label, count, rows, cur, scope }) {
  return (
    <div className="zoom-frame">
      <div className={`step ${cur ? 'cur' : ''}`}>
        <span className="n">{step}</span>{label}
      </div>
      <div className="ct-big"><span className="num">{count}</span> occurrences</div>
      <div className="ct-small">{scope}</div>
      <div style={{ marginBottom: 4 }}>
        <ScopePill steps={[
          { label: 'Corpus', cur: step === 3 },
          { label: 'Hegel',  cur: step === 2 },
          { label: 'PhdG',   cur: step === 1 },
        ]} />
      </div>
      <div style={{ marginTop: 14 }}>
        {rows.map((r, i) => (
          <div key={i} className="mini-row">
            <span className="l">{r.l}</span>
            <span className="m">{r.m}</span>
            <span className="r">{r.r}</span>
          </div>
        ))}
      </div>
      <div className="mini-meta">
        {step === 1 && '⌘+↑ zoom out → author'}
        {step === 2 && '⌘+↑ zoom out → corpus · ⌘+↓ zoom in → work'}
        {step === 3 && '⌘+↓ zoom in → author'}
      </div>
    </div>
  );
}

function F5Desktop({ dark }) {
  return (
    <div className={`wf${dark ? ' dark' : ''}`}>
      <TopNav cur="Concordance" />
      <Side />

      <div style={{ position: 'absolute', top: 44, left: 56, right: 0, height: 80,
                    padding: '18px 32px', borderBottom: '1px solid var(--wf-line-3)' }}>
        <div style={{ fontFamily: 'var(--wf-serif)', fontStyle: 'italic', fontSize: 22 }}>
          Scope zoom · <span style={{ color: 'var(--wf-ink-3)' }}>same lemma, three scales</span>
        </div>
        <div style={{ marginTop: 4, fontFamily: 'var(--wf-sans)', fontSize: 11, color: 'var(--wf-ink-3)', letterSpacing: '0.04em' }}>
          Geist · noun · masc · DEU — the scope pill animates left ↔ right; KWIC rows fade-cross to the new set.
        </div>
      </div>

      <div className="zoom-stage" style={{ top: 124 }}>
        <ZoomFrame step={1} label="Work · Phänomenologie" count="312"   scope="HEGEL · PHDG"     rows={ZOOM_ROWS_WORK}   cur />
        <ZoomFrame step={2} label="Author · Hegel"        count="897"   scope="HEGEL · ALL WORKS" rows={ZOOM_ROWS_AUTHOR} />
        <ZoomFrame step={3} label="Corpus · all German"   count="1,247" scope="CORPUS · DEU"      rows={ZOOM_ROWS_CORPUS} />
      </div>

      <div className="callout t-down" style={{ top: 156, left: 200 }}>
        <span className="num">1</span>
        Step 1 = current. The other two are <em>previews</em>; tapping the
        scope pill animates to that step.
      </div>
      <div className="callout t-up" style={{ top: 260, left: 700 }}>
        <span className="num">2</span>
        Counts grow as you zoom out. The pill segment widens; the count
        morphs in place; KWIC rows cross-fade.
      </div>
      <div className="callout t-left" style={{ top: 380, right: 30 }}>
        <span className="num">3</span>
        Zooming out adds <em>diversity</em> — at corpus you see Kant and
        Nietzsche alongside Hegel. Visible at-a-glance from the row
        contexts.
      </div>
      <div className="callout t-up" style={{ top: 720, left: 200 }}>
        <span className="num">4</span>
        Keyboard: ⌘+↑ / ⌘+↓ step through the three scopes without
        leaving the KWIC view.
      </div>

      <div className="frame-foot">F5 · Scope-zoom transition · three steps shown side-by-side · animated in product</div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════════ */
/* F5 MOBILE                                                     */
/* ════════════════════════════════════════════════════════════ */

function F5Mobile({ dark }) {
  return (
    <div className={`wf mob${dark ? ' dark' : ''}`}>
      <MobShell title="Geist" titleEm="scope" back="KWIC">
        <div className="m-zoom">
          <div className="z-step cur">
            <div className="scope-row"><span className="n">1</span>Work · <b style={{ color: 'var(--wf-ink)' }}>PhdG</b></div>
            <div className="ct-big"><span className="num">312</span> in work</div>
            <div className="mini">… die sittliche Welt ist der <span className="hl">Geist</span>, der seine Wahrheit …</div>
          </div>
          <div className="z-step">
            <div className="scope-row"><span className="n">2</span>Author · Hegel · all works</div>
            <div className="ct-big"><span className="num">897</span> in Hegel</div>
            <div className="mini">… der menschliche <span className="hl">Geist</span> als befreit von aller Sinnlichkeit …</div>
          </div>
          <div className="z-step">
            <div className="scope-row"><span className="n">3</span>Corpus · all German</div>
            <div className="ct-big"><span className="num">1,247</span> in corpus</div>
            <div className="mini">… Sklavenmoral ist dem freien <span className="hl">Geiste</span> das gefährlichste Gift …</div>
          </div>
        </div>
      </MobShell>

      <div className="callout t-right" style={{ top: 120, left: 350 }}>
        <span className="num">1</span>
        Stacked vertically — tap a step to set scope and pop back to the
        KWIC list.
      </div>
      <div className="callout t-up" style={{ top: 360, left: 250 }}>
        <span className="num">2</span>
        Each step shows one representative KWIC row so the user knows what
        zooming out actually buys them.
      </div>
      <div className="callout t-left" style={{ top: 600, right: 30 }}>
        <span className="num">3</span>
        Numbered dots match desktop pill segments — current step inverts.
      </div>

      <div className="frame-foot">F5 · scope picker · mobile</div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════════ */
/* F6 DESKTOP — Empty / loading / error                          */
/* ════════════════════════════════════════════════════════════ */

function F6Desktop({ dark }) {
  return (
    <div className={`wf${dark ? ' dark' : ''}`}>
      <TopNav cur="Concordance" />
      <Side />

      <div className="states-stage">
        {/* A. NO RESULTS */}
        <div className="states-frame">
          <div className="sf-label">A · <b>NO RESULTS</b> · filters too narrow</div>
          <div style={{ padding: '14px 24px', borderBottom: '1px solid var(--wf-line-4)' }}>
            <ScopePill steps={[{ label: 'Hegel' }, { label: 'PhdG', cur: true }]} />
            <div className="m-chips" style={{ padding: '10px 0 0', borderBottom: 0 }}>
              <span className="m-chip on">Gen</span>
              <span className="m-chip on">Pl</span>
              <span className="m-chip on">Geister</span>
            </div>
          </div>
          <div className="empty">
            <div className="icon">∅</div>
            <div className="ttl">No occurrences</div>
            <div className="sub">
              <em>Geister</em> (Gen · Pl) doesn't appear in Phänomenologie
              with the current filters.
            </div>
            <div className="sub" style={{ marginTop: 8 }}>
              <span style={{ color: 'var(--wf-callout)' }}>Drop Number</span> · 3 hits ·{' '}
              <span style={{ color: 'var(--wf-callout)' }}>Zoom to Hegel</span> · 17 hits ·{' '}
              <span style={{ color: 'var(--wf-callout)' }}>Zoom to corpus</span> · 41 hits
            </div>
          </div>
        </div>

        {/* B. LOADING SKELETON */}
        <div className="states-frame">
          <div className="sf-label">B · <b>LOADING</b> · KWIC skeleton</div>
          <div style={{ padding: '14px 24px', borderBottom: '1px solid var(--wf-line-4)' }}>
            <ScopePill steps={[{ label: 'Hegel' }, { label: 'PhdG', cur: true }]} count="…" />
            <div style={{ marginTop: 8, fontFamily: 'var(--wf-sans)', fontSize: 10, color: 'var(--wf-ink-3)', letterSpacing: '0.06em' }}>
              FETCHING /api/works/phdg/term_occurrences?lemma=Geist
            </div>
          </div>
          <div style={{ padding: '6px 0' }}>
            {[1,2,3,4,5,6].map((i) => (
              <div key={i} className="kwic-row skel" style={{ gridTemplateColumns: '88px 1fr 110px 1fr 90px' }}>
                <span className="bar tall" />
                <span className="bar short" />
                <span className="bar match" />
                <span className="bar" />
                <span className="bar tall" style={{ width: '70%' }} />
              </div>
            ))}
          </div>
        </div>

        {/* C. NO LEMMATIZER */}
        <div className="states-frame">
          <div className="sf-label">C · <b>NO LEMMATIZER</b> · cache cold for this edition</div>
          <div style={{ padding: '14px 24px', borderBottom: '1px solid var(--wf-line-4)' }}>
            <ScopePill steps={[{ label: 'Lucretius' }, { label: 'De Rerum Natura', cur: true }]} />
          </div>
          <div className="empty">
            <div className="icon">!</div>
            <div className="ttl">No lemma cache</div>
            <div className="sub">
              spaCy hasn't lemmatised this edition yet. Concordance can't
              key occurrences until the lemma cache lands.
            </div>
            <div className="cmd">$ poietes terms lemmatize --lang lat</div>
            <div className="sub" style={{ marginTop: 4, fontSize: 11.5 }}>
              ~3 min · ~12,000 chunks · runs once per edition.
            </div>
            <span className="act">Run on cluster →</span>
          </div>
        </div>
      </div>

      <div className="callout t-down" style={{ top: 100, left: 220 }}>
        <span className="num">1</span>
        Empty isn't dead-end. Suggest the cheapest broadening move +
        its expected count.
      </div>
      <div className="callout t-down" style={{ top: 100, left: 720 }}>
        <span className="num">2</span>
        Skeleton mimics the row grid so layout doesn't shift on data
        arrival. Six rows max — covers the typical fold.
      </div>
      <div className="callout t-down" style={{ top: 100, left: 1180 }}>
        <span className="num">3</span>
        Cold-cache is an operational state, not user error. Show the
        exact CLI command + offer a one-tap run.
      </div>

      <div className="frame-foot">F6 · Empty · Loading · Error — three side-by-side states</div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════════ */
/* F6 MOBILE — three small sub-frames in the body                */
/* ════════════════════════════════════════════════════════════ */

function F6Mobile({ dark }) {
  return (
    <div className={`wf mob${dark ? ' dark' : ''}`}>
      <MobShell title="States" titleEm="empty · load · error">
        <div style={{ height: '33%', borderBottom: '1px solid var(--wf-line-3)', position: 'relative' }}>
          <div style={{ padding: '8px 14px', fontFamily: 'var(--wf-sans)', fontSize: 9.5,
                       color: 'var(--wf-ink-3)', letterSpacing: '0.12em' }}>
            A · NO RESULTS
          </div>
          <div className="m-empty" style={{ height: 'calc(100% - 26px)', padding: '8px 24px' }}>
            <div className="icon" style={{ width: 36, height: 36, fontSize: 14 }}>∅</div>
            <div className="ttl" style={{ fontSize: 15 }}>No occurrences</div>
            <div className="sub" style={{ fontSize: 11.5 }}>
              <em>Geister</em>·Gen·Pl in PhdG.{' '}
              <span style={{ color: 'var(--wf-callout)' }}>Drop Number</span> · 3 ·{' '}
              <span style={{ color: 'var(--wf-callout)' }}>Hegel</span> · 17
            </div>
          </div>
        </div>

        <div style={{ height: '34%', borderBottom: '1px solid var(--wf-line-3)', position: 'relative' }}>
          <div style={{ padding: '8px 14px', fontFamily: 'var(--wf-sans)', fontSize: 9.5,
                       color: 'var(--wf-ink-3)', letterSpacing: '0.12em' }}>
            B · LOADING · KWIC SKELETON
          </div>
          <div style={{ padding: '0' }}>
            {[1,2,3,4].map((i) => (
              <div key={i} style={{ padding: '10px 14px', background: 'var(--wf-fill)',
                                   borderTop: '1px solid var(--wf-line-4)', marginBottom: 2 }}>
                <div style={{ display: 'flex', gap: 8, marginBottom: 4 }}>
                  <span style={{ height: 12, width: 60, background: 'var(--wf-fill-2)' }} />
                  <span style={{ height: 12, width: 50, background: 'var(--wf-fill-2)', marginLeft: 'auto' }} />
                </div>
                <div style={{ height: 10, width: '90%', background: 'var(--wf-fill-2)', marginBottom: 3 }} />
                <div style={{ height: 10, width: '70%', background: 'var(--wf-fill-2)' }} />
              </div>
            ))}
          </div>
        </div>

        <div style={{ height: '33%', position: 'relative' }}>
          <div style={{ padding: '8px 14px', fontFamily: 'var(--wf-sans)', fontSize: 9.5,
                       color: 'var(--wf-ink-3)', letterSpacing: '0.12em' }}>
            C · NO LEMMATIZER
          </div>
          <div className="m-empty" style={{ height: 'calc(100% - 26px)', padding: '6px 24px' }}>
            <div className="icon" style={{ width: 36, height: 36, fontSize: 14 }}>!</div>
            <div className="ttl" style={{ fontSize: 15 }}>No lemma cache</div>
            <div className="cmd" style={{ fontSize: 10 }}>$ poietes terms lemmatize --lang lat</div>
          </div>
        </div>
      </MobShell>

      <div className="callout t-right" style={{ top: 110, left: 350 }}>
        <span className="num">1</span>
        At mobile we stack the three states inside one screen for the
        wireframe — in production they are three separate routes.
      </div>
      <div className="callout t-left" style={{ top: 420, right: 30 }}>
        <span className="num">2</span>
        Skeleton at mobile = compact stacked rows · same row anatomy
        as F2 mobile so layout stays put.
      </div>

      <div className="frame-foot">F6 · states · mobile composite</div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════════ */
/* App                                                           */
/* ════════════════════════════════════════════════════════════ */

function App() {
  const DW = 1440, DH = 900;
  const MW = 390,  MH = 844;
  return (
    <DesignCanvas>
      <DCSection id="intro" title="Concordance — wireframes" subtitle="6 screens × 2 form factors. Greyscale boxes-and-labels; real German lemmas. Light theme shown — dark parchment derives from the documented palette and is not redrawn here.">
        <DCArtboard id="legend" label="Conventions" width={520} height={300}>
          <div className="wf" style={{ padding: 22, fontSize: 12, lineHeight: 1.6 }}>
            <div style={{ fontFamily: 'var(--wf-serif)', fontStyle: 'italic', fontSize: 20, marginBottom: 10 }}>
              Reading these wireframes
            </div>
            <div style={{ fontFamily: 'var(--wf-label)', color: 'var(--wf-ink-2)', fontSize: 12, lineHeight: 1.6 }}>
              <p style={{ margin: '0 0 8px' }}>
                <b style={{ color: 'var(--wf-ink)' }}>Oxblood callouts</b> = annotations of non-obvious interactions; numbered to read in order.
              </p>
              <p style={{ margin: '0 0 8px' }}>
                <b style={{ color: 'var(--wf-ink)' }}>Italic serif</b> = lemma, match, gloss. <b style={{ color: 'var(--wf-ink)' }}>Mono</b> = locator, count, morphology. <b style={{ color: 'var(--wf-ink)' }}>Sans</b> = UI labels.
              </p>
              <p style={{ margin: '0 0 8px' }}>
                <b style={{ color: 'var(--wf-ink)' }}>Greyscale fills</b> — paper-soft <span style={{ display: 'inline-block', width: 14, height: 10, background: 'var(--wf-fill)', border: '1px solid var(--wf-line-3)', verticalAlign: -1 }} /> for cards, ink <span style={{ display: 'inline-block', width: 14, height: 10, background: 'var(--wf-ink)', verticalAlign: -1 }} /> for inverted CTAs, dashed grey for stubbed app chrome.
              </p>
              <p style={{ margin: '0 0 8px' }}>
                <b style={{ color: 'var(--wf-ink)' }}>KWIC row anatomy</b> — locator · LEFT (right-fading) · <em style={{ color: 'var(--wf-callout)' }}>match</em> · RIGHT (left-fading) · morphology. Centered match is the classical concordance affordance; this is what every screen optimizes for.
              </p>
            </div>
          </div>
        </DCArtboard>
      </DCSection>

      <DCSection id="s1" title="01 · Lemma frequency index" subtitle="Top-nav entry. Leaderboard + A–Z rail + scope picker. Corpus-scoped by default (no work required).">
        <DCArtboard id="f1d" label="1a · Desktop · 1440×900" width={DW} height={DH}><F1Desktop /></DCArtboard>
        <DCArtboard id="f1m" label="1b · Mobile · 390×844"  width={MW} height={MH}><F1Mobile /></DCArtboard>
      </DCSection>

      <DCSection id="s2" title="02 · Lemma detail / KWIC grid" subtitle="The heart of the concordance. Centered match, two fading contexts, morphology + filter rail.">
        <DCArtboard id="f2d" label="2a · Desktop · KWIC grid" width={DW} height={DH}><F2Desktop /></DCArtboard>
        <DCArtboard id="f2m" label="2b · Mobile · stacked KWIC"  width={MW} height={MH}><F2Mobile /></DCArtboard>
      </DCSection>

      <DCSection id="s3" title="03 · Reader sidebar · Concordance tab" subtitle="Third tab alongside Word and Notes. In-work scope by default; lemma mini-list sorted by local frequency.">
        <DCArtboard id="f3d" label="3a · Desktop · sidebar" width={DW} height={DH}><F3Desktop /></DCArtboard>
        <DCArtboard id="f3m" label="3b · Mobile · drawer"  width={MW} height={MH}><F3Mobile /></DCArtboard>
      </DCSection>

      <DCSection id="s4" title="04 · TermCard · See-all CTA" subtitle="Active + hover state of the existing TermCard's stub button. Inline scope-preview tooltip on hover.">
        <DCArtboard id="f4d" label="4a · Desktop · hover state" width={DW} height={DH}><F4Desktop /></DCArtboard>
        <DCArtboard id="f4m" label="4b · Mobile · bottom sheet"  width={MW} height={MH}><F4Mobile /></DCArtboard>
      </DCSection>

      <DCSection id="s5" title="05 · Scope-zoom transition" subtitle="work → author → corpus. The scope pill animates left/right; KWIC cross-fades to the new set.">
        <DCArtboard id="f5d" label="5a · Desktop · three steps" width={DW} height={DH}><F5Desktop /></DCArtboard>
        <DCArtboard id="f5m" label="5b · Mobile · vertical picker"  width={MW} height={MH}><F5Mobile /></DCArtboard>
      </DCSection>

      <DCSection id="s6" title="06 · Empty · Loading · Error" subtitle="No-results suggests the cheapest broadening move. Skeleton mirrors the row grid. Cold-cache is a CLI hand-off, not an error tone.">
        <DCArtboard id="f6d" label="6a · Desktop · three states" width={DW} height={DH}><F6Desktop /></DCArtboard>
        <DCArtboard id="f6m" label="6b · Mobile · composite"  width={MW} height={MH}><F6Mobile /></DCArtboard>
      </DCSection>
    </DesignCanvas>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
