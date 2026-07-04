// Translate-rail state machine. Owns the rail signal, the target
// language, and the inflight controller that races stale translations.
// Callers fire `runTranslate(source, ref)` from word clicks, selection
// commits, or saved-marker clicks; the hook handles abortion when a
// new request comes in.

import { createSignal, onCleanup } from "solid-js";
import { translate } from "~/api/readerApi";
import { errorMessage, isAbortError } from "~/utils/util";
import type { TargetLang } from "~/utils/types";
import type { RailState } from "~/Reader/types";

export interface TranslateRailApi {
  rail: () => RailState;
  target: () => TargetLang;
  /** Change target language. Re-runs any ready/error rail in the new
   *  language; promotes idle to "awaiting" so the lang chips visibly
   *  affect something before the user selects text. Pass
   *  ``{ promote: false }`` for a programmatic default shift that must
   *  not open the rail (issue #63). */
  setTargetLang: (t: TargetLang, opts?: { promote?: boolean }) => void;
  /** Fire-and-forget translation. Cancels any prior inflight. */
  runTranslate: (source: string, ref: string) => void;
  /** Re-run the source/ref of the current error state, if any. */
  retry: () => void;
  /** Abort and reset to idle. */
  reset: () => void;
}

export function useTranslateRail(): TranslateRailApi {
  const [rail, setRail] = createSignal<RailState>({ kind: "idle" });
  const [target, setTarget] = createSignal<TargetLang>("eng");
  let inflightController: AbortController | undefined;

  async function runTranslateInternal(source: string, ref: string) {
    inflightController?.abort();
    const controller = new AbortController();
    inflightController = controller;
    setRail({ kind: "loading", source, ref });
    try {
      const response = await translate(source, target(), controller.signal);
      if (inflightController === controller) {
        setRail({ kind: "ready", source, ref, response });
      }
    } catch (err) {
      if (isAbortError(err)) return;
      const message = errorMessage(err);
      if (inflightController === controller) {
        setRail({ kind: "error", source, ref, message });
      }
    } finally {
      if (inflightController === controller) {
        inflightController = undefined;
      }
    }
  }

  function runTranslate(source: string, ref: string) {
    void runTranslateInternal(source, ref);
  }

  function retry() {
    const r = rail();
    if (r.kind === "error") runTranslate(r.source, r.ref);
  }

  function setTargetLang(t: TargetLang, opts?: { promote?: boolean }) {
    setTarget(t);
    const r = rail();
    if (r.kind === "ready" || r.kind === "error") {
      // Server cache hits if the (source, lang) pair was seen before.
      runTranslate(r.source, r.ref);
      return;
    }
    // A programmatic default shift (e.g. auto-target on an English
    // work) must not promote idle→awaiting — that pops an empty rail
    // before the user has asked for anything (issue #63).
    if (opts?.promote === false) return;
    if (r.kind === "idle" || r.kind === "awaiting") {
      setRail({ kind: "awaiting" });
    }
  }

  function reset() {
    inflightController?.abort();
    inflightController = undefined;
    setRail({ kind: "idle" });
  }

  // Abort any inflight request when the owning component disposes.
  // Plain onCleanup — the old createEffect wrapper had no tracked
  // reads, so it was just a roundabout way of registering the same
  // disposal-time cleanup.
  onCleanup(() => inflightController?.abort());

  return { rail, target, setTargetLang, runTranslate, retry, reset };
}
