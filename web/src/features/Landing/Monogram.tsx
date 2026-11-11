// The landing's mark and the epigraph it carries.
//
// Alternate logo: the owl-of-Athena is the default mark; on ~1-in-5 page
// loads we instead render the rose-in-the-cross with the Hegel/Marx epigraph
// below it — Hegel's Preface to the Philosophy of Right ("Hic Rhodus, hic
// salta — Hier ist die Rose, hier tanze") that Marx picks up in the 18th
// Brumaire. Random per mount so it reads as a quiet Easter egg rather than a
// feature.

import type { JSX } from "solid-js";

export const ROSE_LOGO_PROBABILITY = 0.2;

// Landing renders once per app, so a module constant is enough to tie the
// monogram to the epigraph it describes.
const TOOLTIP_ID = "landing-monogram-tooltip";

interface Logo {
  src: string;
  /** The rose's epigraph is a paragraph, and needs the wider tooltip. */
  long: boolean;
  /** A function, not JSX: a module-level element would be one DOM node,
   *  moved rather than copied each time the landing mounts again. */
  epigraph: () => JSX.Element;
}

const OWL: Logo = {
  src: "/owl.png",
  long: false,
  epigraph: () => (
    <>
      <span class="t1">What is rational is actual,</span>
      <span class="t2">and what is actual is rational.</span>
      <span class="landing-monogram-tooltip-epigraph">
        <span lang="de">
          Die Eule der Minerva beginnt erst mit der einbrechenden Dämmerung ihren Flug.
        </span>
        <span>The owl of Minerva spreads its wings only with the falling of the dusk.</span>
      </span>
    </>
  ),
};

const ROSE: Logo = {
  src: "/rose-cross.png",
  long: true,
  epigraph: () => (
    <>
      <span class="t1">
        To recognize reason as the rose within the cross of the present and thereby delight in the
        present — this rational insight is the reconciliation with actuality which philosophy grants
        to those who've received the inner call to comprehend, to preserve their subjective freedom
        not in a particular and contingent situation, but in what has being in and for itself.
      </span>
      <span class="landing-monogram-tooltip-epigraph">
        <span lang="la">Hic Rhodus, hic salta.</span>
        <span lang="de">Hier ist die Rose, hier tanze.</span>
      </span>
    </>
  ),
};

export default function Monogram() {
  const logo = Math.random() < ROSE_LOGO_PROBABILITY ? ROSE : OWL;
  return (
    <div class="landing-monogram-wrap">
      {/* A button rather than a `tabindex`-bearing div: the mark is a tab
          stop only so the epigraph beside it can be reached without a mouse
          (`.landing-monogram:focus-visible + .landing-monogram-tooltip`,
          landing.css), and a bare tab stop with no role and no name
          announces nothing. `aria-describedby` is what actually reads the
          epigraph out; before it the `role="tooltip"` element was orphaned. */}
      <button type="button" class="landing-monogram" aria-describedby={TOOLTIP_ID}>
        <img src={logo.src} alt="Minerva" class="landing-monogram-owl" />
      </button>
      <div
        id={TOOLTIP_ID}
        class={`landing-monogram-tooltip${logo.long ? " landing-monogram-tooltip-long" : ""}`}
        role="tooltip"
      >
        {logo.epigraph()}
      </div>
    </div>
  );
}
