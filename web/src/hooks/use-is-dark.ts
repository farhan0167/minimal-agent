import { useSyncExternalStore } from "react";

function subscribe(callback: () => void) {
  const observer = new MutationObserver(callback);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["class"],
  });
  return () => observer.disconnect();
}

/**
 * Whether dark mode is currently active, reacting to the `.dark` class on
 * <html> (the single source of truth set by use-theme.ts). Unlike useTheme,
 * this observes the DOM, so it stays correct no matter which component
 * instance toggled the theme.
 */
export function useIsDark(): boolean {
  return useSyncExternalStore(subscribe, () =>
    document.documentElement.classList.contains("dark"),
  );
}
