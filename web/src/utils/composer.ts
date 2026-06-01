// Shared textarea/send state for the two compose surfaces: the landing
// page's "Begin" textarea and the in-thread Composer. They diverge only
// in placement, autosize bounds, whether the field clears after sending,
// and an optional disabled gate (the in-thread Composer locks out
// while a reply is in flight). The Enter / Shift+Enter / trim / no-op
// on empty logic is identical and lives here.

import { createSignal } from "solid-js";
import { fitTextAreaHeight } from "~/utils/fitTextarea";

export interface ComposerOptions {
  /** Min textarea height in CSS px; collapses to this when empty. */
  minPx: number;
  /** Max textarea height before scrolling. */
  maxPx: number;
  /** Called with the trimmed value on submit. No-op when empty. */
  onSubmit: (text: string) => void;
  /** When true, the field clears and re-autosizes after a successful
   *  submit. Composer uses this; Landing keeps the text so the user
   *  sees what they sent during the route transition. */
  clearOnSend?: boolean;
  /** Reactive disabled gate. When it returns true, Enter and click
   *  are no-ops. Independent of the textarea's own `disabled` HTML
   *  attribute (which the caller still has to set). */
  isDisabled?: () => boolean;
}

export interface ComposerState {
  value: () => string;
  setValue: (v: string) => void;
  /** Pass as `ref={setRef}` on the textarea. */
  setRef: (el: HTMLTextAreaElement) => void;
  /** Resize to fit current content within the [min, max] bounds. */
  autosize: () => void;
  /** Submit the trimmed value (if non-empty and not disabled). */
  send: () => void;
  /** Bind to the textarea's `onInput`. */
  onInput: (e: InputEvent & { currentTarget: HTMLTextAreaElement }) => void;
  /** Bind to the textarea's `onKeyDown`. Implements Enter = send,
   *  Shift+Enter = newline. */
  onKeyDown: (e: KeyboardEvent) => void;
  /** True when the field is empty or the disabled gate is set; used
   *  by the send button's class and `disabled` attribute. */
  sendDisabled: () => boolean;
}

export function createComposer(opts: ComposerOptions): ComposerState {
  const [value, setValueSignal] = createSignal("");
  let taRef: HTMLTextAreaElement | undefined;

  const setRef = (el: HTMLTextAreaElement) => {
    taRef = el;
  };
  const autosize = () => {
    fitTextAreaHeight(taRef, opts.minPx, opts.maxPx);
  };

  function send() {
    if (opts.isDisabled?.()) return;
    const v = value().trim();
    if (!v) return;
    opts.onSubmit(v);
    if (opts.clearOnSend) {
      setValueSignal("");
      // After clearing, the next paint will measure scrollHeight against
      // the empty content; queue so we resize *after* the DOM reflects
      // the cleared value.
      queueMicrotask(autosize);
    }
  }

  function onInput(e: InputEvent & { currentTarget: HTMLTextAreaElement }) {
    setValueSignal(e.currentTarget.value);
    autosize();
  }

  function onKeyDown(e: KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  const sendDisabled = () => (opts.isDisabled?.() ?? false) || !value().trim();

  return {
    value,
    setValue: setValueSignal,
    setRef,
    autosize,
    send,
    onInput,
    onKeyDown,
    sendDisabled,
  };
}
