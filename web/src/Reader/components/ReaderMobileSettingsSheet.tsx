import { For, createSignal, onMount } from "solid-js";
import type { TargetLang } from "~/utils/types";
import { MobileSheet } from "~/components/shell/MobileSheet";
import { TargetLangToggle } from "~/Reader/components/TargetLangToggle";

const STORAGE_KEY = "minerva-reader-text-scale";
const SCALES = [
  { key: "s", label: "S", size: "16px" },
  { key: "m", label: "M", size: "18.5px" },
  { key: "l", label: "L", size: "20px" },
] as const;

export function ReaderMobileSettingsSheet(props: {
  open: boolean;
  target: TargetLang;
  onTarget: (t: TargetLang) => void;
  onClose: () => void;
}) {
  const [scale, setScale] = createSignal<(typeof SCALES)[number]["key"]>("m");

  onMount(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    const match = SCALES.find((s) => s.key === saved);
    if (match) {
      setScale(match.key);
      document.documentElement.style.setProperty("--reader-text-size", match.size);
    }
  });

  function pickScale(key: (typeof SCALES)[number]["key"]) {
    setScale(key);
    const item = SCALES.find((s) => s.key === key)!;
    localStorage.setItem(STORAGE_KEY, key);
    document.documentElement.style.setProperty("--reader-text-size", item.size);
  }

  return (
    <MobileSheet open={props.open} title="Reader settings" onClose={props.onClose}>
      <section class="reader-settings-section">
        <h3>Translation language</h3>
        <TargetLangToggle
          variant="sheet"
          target={props.target}
          onTarget={props.onTarget}
        />
      </section>
      <section class="reader-settings-section">
        <h3>Text size</h3>
        <div class="reader-scale-toggle">
          <For each={SCALES}>
            {(s) => (
              <button
                type="button"
                class={"reader-scale-btn" + (scale() === s.key ? " active" : "")}
                onClick={() => pickScale(s.key)}
              >
                {s.label}
              </button>
            )}
          </For>
        </div>
      </section>
    </MobileSheet>
  );
}
