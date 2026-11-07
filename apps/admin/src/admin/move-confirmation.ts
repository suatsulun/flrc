/** Set for the rest of the browser session once the admin ticks "do not ask again". */
const SKIP_KEY = "flrc.admin.skipMoveConfirmation";

/** Whether the admin chose to stop confirming student moves for this browser session. */
export function moveConfirmationSkipped(): boolean {
  return sessionStorage.getItem(SKIP_KEY) === "1";
}

/** Stop confirming student moves until the browser session ends. */
export function skipMoveConfirmation(): void {
  sessionStorage.setItem(SKIP_KEY, "1");
}
