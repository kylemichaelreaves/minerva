import { fireEvent as baseFireEvent } from "@solidjs/testing-library";
import { flush } from "solid-js";

/** `fireEvent`, with a Solid `flush()` after every event.
 *
 *  Solid 2 applies signal writes when its scheduler flushes (a microtask), and
 *  a real user's next event always arrives after that. A synchronous test
 *  that fires events back to back never yields, so without this each
 *  assertion — and each next event — would see the UI as it was before the
 *  previous one. Flushing per event models the timing a user actually has;
 *  it does not hide a missing update, because the flush happens either way. */
export const fireEvent = new Proxy(baseFireEvent, {
  get(target, key: keyof typeof baseFireEvent) {
    const fire = target[key] as (...args: unknown[]) => boolean;
    return (...args: unknown[]) => {
      const result = fire(...args);
      flush();
      return result;
    };
  },
});
