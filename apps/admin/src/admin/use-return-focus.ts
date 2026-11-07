import { useRef } from "react";

/**
 * Return focus to the control that opened a dialog. Base UI does this only for its own
 * `DialogTrigger`; dialogs opened from state need the opener remembered. When the opener is
 * gone (a removed row, a toolbar that closed), focus falls back to Base UI's default.
 */
export function useReturnFocus() {
  const opener = useRef<HTMLElement | null>(null);
  return {
    remember: (element: EventTarget | null) => {
      opener.current = element instanceof HTMLElement ? element : null;
    },
    finalFocus: () => (opener.current?.isConnected ? opener.current : true),
  };
}
