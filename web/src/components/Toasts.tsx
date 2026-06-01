// Toast stack for `apiError` user-visible notifications.
//
// Mount once in App.tsx; the component reads the module-level signal
// in `apiError.ts` so any call to `apiError(message)` from anywhere
// in the app surfaces immediately without prop drilling.
//
// Design notes:
//  - Position: fixed bottom-right (out of the way of the reader
//    column + composer). One column, newest on the bottom.
//  - aria-live="polite" so screen readers announce the error once it
//    settles, but don't interrupt mid-utterance.
//  - Each toast has a close (×) button for manual dismissal in
//    addition to the auto-dismiss timer in apiError().

import { For } from "solid-js";
import { dismissToast, useToasts } from "~/utils/apiError";
import "~/components/Toasts.css";

export default function Toasts() {
  const toasts = useToasts();
  return (
    <div class="toasts" role="status" aria-live="polite">
      <For each={toasts()}>
        {(t) => (
          <div class="toast">
            <span class="toast-message">{t.message}</span>
            <button
              type="button"
              class="toast-close"
              aria-label="Dismiss"
              onClick={() => { dismissToast(t.id); }}
            >
              ×
            </button>
          </div>
        )}
      </For>
    </div>
  );
}
