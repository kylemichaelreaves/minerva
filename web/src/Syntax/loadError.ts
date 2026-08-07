import { ApiError } from "~/api/client";

/**
 * What the overlay says when it cannot load a chunk's syntax.
 *
 * The same split `corrections/store.ts` makes for a refused *edit*, applied to
 * the fetch. A 4xx is the server judging this chunk and saying why — since
 * #231, `load_or_parse` refuses a non-German chunk with the language it found:
 *
 *     syntax parsing is deu-only; chunk 'rep-509d' is 'eng'
 *
 * Collapsing that to the generic line leaves a reader unable to tell a text
 * the tool does not handle from a server that is down, and a developer opening
 * the network tab to learn something the response already said (#235).
 *
 * A 5xx or a dropped socket is not a judgement about the passage, so it keeps
 * the generic wording — reporting "502 Bad Gateway" where the reason goes
 * would say something false about the text.
 */
export function loadErrorMessage(err: unknown): string {
  if (err instanceof ApiError && err.status < 500 && err.message) return err.message;
  return "Could not load syntax for this passage.";
}
