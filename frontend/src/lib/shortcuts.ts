// Keyboard shortcuts. They only move focus or navigate; none of them acts on data.

interface KeyLike {
  key: string;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
}

/** Ctrl+K on Windows and Linux, ⌘K on macOS: opens quick navigation. */
export function isCommandShortcut(event: KeyLike): boolean {
  return event.key.toLowerCase() === "k" && (event.ctrlKey || event.metaKey) && !event.altKey;
}

/** "/" with no modifier: focuses the page's search field. */
export function isSearchShortcut(event: KeyLike): boolean {
  return event.key === "/" && !event.ctrlKey && !event.metaKey && !event.altKey;
}

/** True when a keystroke belongs to a field the person is typing in, so shortcuts stay out of the way. */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

export const MODIFIER_LABEL =
  typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.userAgent) ? "⌘" : "Ctrl";
