import { useCallback, useRef, type KeyboardEvent, type RefObject } from "react";

/**
 * Spreadsheet keyboard model for the grade grid.
 *
 * Cells register themselves by `row:column`, so movement is a map lookup rather
 * than a DOM query — it stays instant on a full roster.
 *
 * ── Horizontal keys ────────────────────────────────────────────────────────────
 * Arrow-left/right have to serve two jobs: moving between cells, and moving the
 * caret inside a comment. The selection state decides, which lands on the
 * behaviour teachers expect without a mode to learn:
 *
 *   - the whole value is selected (true right after focus) → move cell
 *   - the caret sits at the very start / end → move cell
 *   - otherwise → let the caret move within the text
 *
 * ── Scrolling ──────────────────────────────────────────────────────────────────
 * The browser only scrolls a focused cell into view at the window edges, but the
 * app header and the column headings stick over the top rows and the `footer`
 * (the save bar) over the bottom ones. Movement reveals the cell itself instead:
 * one even partly behind them jumps to the middle of the rows that stay visible.
 */
export function useGridKeyboard(footer: RefObject<HTMLElement | null>) {
  const cells = useRef(new Map<string, HTMLElement>());

  const register = useCallback(
    (row: number, column: number) => (element: HTMLElement | null) => {
      const key = `${row}:${column}`;
      if (element) cells.current.set(key, element);
      else cells.current.delete(key);
    },
    [],
  );

  const focusCell = useCallback(
    (row: number, column: number) => {
      const target = cells.current.get(`${row}:${column}`);
      if (!target) return false;
      target.focus({ preventScroll: true });
      reveal(target, footer.current);
      return true;
    },
    [footer],
  );

  const onNavKey = useCallback(
    (row: number, column: number) => (event: KeyboardEvent) => {
      const { key, shiftKey, metaKey, ctrlKey, altKey } = event;
      if (metaKey || ctrlKey || altKey) return;

      const move = (rowDelta: number, columnDelta: number) => {
        if (focusCell(row + rowDelta, column + columnDelta)) event.preventDefault();
      };

      if (key === "ArrowDown" || (key === "Enter" && !shiftKey)) return move(1, 0);
      if (key === "ArrowUp" || (key === "Enter" && shiftKey)) return move(-1, 0);
      if (key !== "ArrowLeft" && key !== "ArrowRight") return;

      const element = event.currentTarget;
      if (!(element instanceof HTMLInputElement)) {
        return move(0, key === "ArrowLeft" ? -1 : 1);
      }

      const { selectionStart, selectionEnd, value } = element;
      const allSelected = selectionStart === 0 && selectionEnd === value.length;
      if (key === "ArrowLeft" && (allSelected || selectionStart === 0)) return move(0, -1);
      if (key === "ArrowRight" && (allSelected || selectionEnd === value.length)) return move(0, 1);
    },
    [focusCell],
  );

  return { register, onNavKey };
}

function reveal(cell: HTMLElement, footer: HTMLElement | null) {
  const { top, bottom } = cell.getBoundingClientRect();
  // Every heading sticks at the same offset, so the first one's lower edge is
  // where the visible rows begin, whether or not the headings are stuck yet.
  const headings = cell.closest("table")?.querySelector("th");
  const visibleTop = Math.max(0, headings?.getBoundingClientRect().bottom ?? 0);
  const visibleBottom = Math.min(
    document.documentElement.clientHeight,
    footer?.getBoundingClientRect().top ?? Infinity,
  );
  if (top >= visibleTop && bottom <= visibleBottom) return;
  window.scrollTo({
    top: window.scrollY + (top + bottom) / 2 - (visibleTop + visibleBottom) / 2,
  });
}
