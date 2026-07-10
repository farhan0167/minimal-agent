/**
 * Abort/disconnect classification, adapted from llama.cpp's webui.
 *
 * Browsers surface a torn-down stream inconsistently: a user Stop or page
 * navigation raises AbortError, but Safari/Firefox report a mid-read network
 * loss as a plain TypeError with a browser-specific message. None of these
 * should render as a red error in the chat.
 */
const NETWORK_ABORT_PHRASES = [
  "input stream", // Firefox: "Error in input stream"
  "network connection was lost", // Safari
  "load failed", // Safari fetch failure
  "fetch is aborted",
  "networkerror when attempting to fetch",
];

export function isAbortError(err: unknown): boolean {
  if (err instanceof DOMException && err.name === "AbortError") return true;
  if (err instanceof TypeError) {
    const message = err.message.toLowerCase();
    return NETWORK_ABORT_PHRASES.some((phrase) => message.includes(phrase));
  }
  return false;
}
