import { render } from "@solidjs/testing-library";
import { describe, expect, it } from "vitest";
import {
  SuspendedSubtreeProvider,
  useSuspendedSubtree,
} from "~/hooks/suspendedSubtree";

// The scoping property the #352 fix rests on: a hook answers "am I inside the
// suspended subtree?", never "does the app have a suspended subtree
// somewhere?". The concordance renders in a sibling of the Reader's wrapper,
// so it must read the default and keep every listener it owns.

function Probe(props: { onRead: (v: boolean) => void }) {
  const suspended = useSuspendedSubtree();
  props.onRead(suspended());
  return <div />;
}

describe("the suspended-subtree context", () => {
  it("reads false with no provider above it", () => {
    // The case that keeps the concordance's own Select, its list-keyboard
    // navigation and every destination route working while a Reader is
    // retained beside them.
    let seen: boolean | undefined;
    render(() => <Probe onRead={(v) => (seen = v)} />);

    expect(seen).toBe(false);
  });

  it("reads the provider's value inside it", () => {
    let seen: boolean | undefined;
    render(() => (
      <SuspendedSubtreeProvider suspended={() => true}>
        <Probe onRead={(v) => (seen = v)} />
      </SuspendedSubtreeProvider>
    ));

    expect(seen).toBe(true);
  });

  it("stays reactive to the provider's accessor", () => {
    // `suspended` is threaded as an accessor, not a snapshot: the Reader
    // flips between retained and showing without remounting, so a captured
    // boolean would pin every listener to whichever state it mounted in.
    const reads: boolean[] = [];
    let suspended = false;
    render(() => (
      <SuspendedSubtreeProvider suspended={() => suspended}>
        <Probe onRead={(v) => reads.push(v)} />
      </SuspendedSubtreeProvider>
    ));
    suspended = true;
    render(() => (
      <SuspendedSubtreeProvider suspended={() => suspended}>
        <Probe onRead={(v) => reads.push(v)} />
      </SuspendedSubtreeProvider>
    ));

    expect(reads).toEqual([false, true]);
  });
});
