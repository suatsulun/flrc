import { expect } from "@playwright/test";
import type { Locator } from "@playwright/test";

/**
 * Layout contract for a table surface under ADR-045.
 *
 * Tables own a bounded scroll viewport instead of stretching the page, so the
 * checks are about the viewport containing the overflow while every column
 * stays reachable and readable.
 */
export type TableSurfaceMetrics = {
  overflowX: string;
  overflowY: string;
  hasCaption: boolean;
  pageFits: boolean;
  headersReadable: boolean;
  lastColumnReachable: boolean;
  firstColumnPinned: boolean;
  pinnedColumnsAligned: boolean;
};

export async function tableSurfaceMetrics(surface: Locator): Promise<TableSurfaceMetrics> {
  return surface.evaluate((element) => {
    const root = document.documentElement;
    const headers = [...element.querySelectorAll("th")];
    const firstHeader = headers[0];
    // Utility columns (drag handle, row actions) carry only a screen-reader
    // label, and the trailing slack column carries none at all, so both are
    // exempt from the readable-size rule and from the reachability check.
    const visibleLabel = (header: HTMLTableCellElement) => {
      const clone = header.cloneNode(true) as HTMLTableCellElement;
      for (const hidden of clone.querySelectorAll(".sr-only")) hidden.remove();
      return clone.textContent?.trim() ?? "";
    };
    const labelledHeaders = headers.filter((header) => visibleLabel(header));
    const lastHeader = labelledHeaders.at(-1);
    const restoreScrollLeft = element.scrollLeft;
    element.scrollLeft = element.scrollWidth;
    // Measure against the viewport's content box: the card border and the
    // reserved scrollbar gutter are not part of the scrollable area, so a
    // pinned column sits inside them rather than on the border box edge.
    const box = element.getBoundingClientRect();
    const viewportLeft = box.left + Number.parseFloat(getComputedStyle(element).borderLeftWidth);
    const viewportRight = viewportLeft + element.clientWidth;
    const metrics = {
      overflowX: getComputedStyle(element).overflowX,
      overflowY: getComputedStyle(element).overflowY,
      hasCaption: Boolean(element.querySelector("table > caption")),
      pageFits: root.scrollWidth <= root.clientWidth + 1,
      headersReadable: labelledHeaders.every((header) => {
        const style = getComputedStyle(header);
        return (
          header.getBoundingClientRect().width >= 56 && Number.parseFloat(style.fontSize) >= 12
        );
      }),
      lastColumnReachable: Boolean(
        lastHeader && lastHeader.getBoundingClientRect().right <= viewportRight + 1,
      ),
      firstColumnPinned: Boolean(
        firstHeader && Math.abs(firstHeader.getBoundingClientRect().left - viewportLeft) <= 1,
      ),
      // Pinned columns are stacked with fixed `left` offsets that assume the
      // declared column widths. If surplus table width inflates those columns,
      // sticky clamps them inside the table and the stack gaps or overlaps.
      pinnedColumnsAligned: headers
        .filter((header) => {
          const style = getComputedStyle(header);
          return style.position === "sticky" && style.left !== "auto";
        })
        .every((header, index, pinned) => {
          const box = header.getBoundingClientRect();
          const expected =
            index === 0 ? viewportLeft : pinned[index - 1].getBoundingClientRect().right;
          return Math.abs(box.left - expected) <= 1;
        }),
    };
    element.scrollLeft = restoreScrollLeft;
    return metrics;
  });
}

/** Assert the full ADR-045 contract for one table surface. */
export async function expectContainedTable(surface: Locator): Promise<void> {
  await expect(surface).toBeVisible();
  await expect
    .poll(() => tableSurfaceMetrics(surface))
    .toEqual({
      overflowX: "auto",
      overflowY: "auto",
      hasCaption: true,
      pageFits: true,
      headersReadable: true,
      lastColumnReachable: true,
      firstColumnPinned: true,
      pinnedColumnsAligned: true,
    });
}

/** Paginated teacher assessments stay readable within the page (ADR-049). */
export async function expectFocusedTable(surface: Locator): Promise<void> {
  await expect(surface).toBeVisible();
  await expect(surface.locator("caption")).toHaveText("Grade-entry table");
  await expect
    .poll(() => surface.locator('[data-testid="assessment-heading"]').count())
    .toBeGreaterThan(0);
  const layout = await surface.evaluate((element) => ({
    pageFits: document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
    tableFits: element.scrollWidth <= element.clientWidth + 1,
    readable: [...element.querySelectorAll("th")].every(
      (header) => parseFloat(getComputedStyle(header).fontSize) >= 14,
    ),
    maxColumns: element.querySelectorAll('[data-testid="assessment-heading"]').length <= 3,
    pageScroll: getComputedStyle(element).overflowY === "visible",
  }));
  expect(layout).toEqual({
    pageFits: true,
    tableFits: true,
    readable: true,
    maxColumns: true,
    pageScroll: true,
  });
}
