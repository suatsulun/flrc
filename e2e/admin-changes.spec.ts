import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import type { AdminActionOut, AdminActionPage, MeOut } from "../packages/api-client/src/index";
import { adminOrigin } from "./helpers/origins";

const en = JSON.parse(readFileSync("packages/i18n/src/locales/en.json", "utf8")) as {
  changes: {
    title: string;
    undo: string;
    undone: string;
    loadMore: string;
    confirmTitle: string;
    statuses: { available: string; expired: string };
  };
};

const DAY_MS = 24 * 60 * 60 * 1000;

const admin: MeOut = {
  id: 1,
  full_name: "Synthetic Admin",
  email: "admin@example.test",
  is_admin: true,
  is_coordinator: false,
  assignments: [],
};

function action(id: number, fields: Partial<AdminActionOut>): AdminActionOut {
  return {
    id,
    kind: "class.create",
    actor: "Synthetic Admin",
    created_at: new Date(Date.now() - DAY_MS).toISOString(),
    // Three days and a little time left: the badge counts whole days up.
    expires_at: new Date(Date.now() + 3 * DAY_MS - 60_000).toISOString(),
    status: "available",
    undone_at: null,
    undone_by: null,
    params: {},
    ...fields,
  };
}

const move = action(32, {
  kind: "student.move",
  params: { count: 1, students: ["Synthetic Pupil"], from_classes: ["8/A"], to_class: "8/B" },
});
const created = action(31, { kind: "class.create", params: { class: "8/C" } });
const expired = action(30, {
  kind: "field.copy",
  status: "expired",
  expires_at: new Date(Date.now() - DAY_MS).toISOString(),
  params: {
    count: 4,
    from_grade_level: 5,
    from_subject: "english",
    to_grade_level: 6,
    to_subject: "english",
  },
});

/** Every request stays in this browser context; nothing touches a school database. */
async function mockApi(page: Page, me: MeOut = admin) {
  let classUndone = false;
  await page.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path === "/api/me") return route.fulfill({ json: me });
    if (path === "/api/admin/actions") {
      const current = classUndone
        ? {
            ...created,
            status: "undone" as const,
            undone_at: new Date().toISOString(),
            undone_by: "Synthetic Admin",
          }
        : created;
      const body: AdminActionPage = url.searchParams.has("cursor")
        ? { items: [expired], next_cursor: null }
        : { items: [move, current], next_cursor: 31 };
      return route.fulfill({ json: body });
    }
    // The pupil's old number went to someone else: the API refuses and names the holder.
    if (path === "/api/admin/actions/32/undo") {
      return route.fulfill({
        status: 409,
        json: {
          detail: {
            code: "undo_blocked",
            reason: "school_number_taken",
            params: { number: 123, student: "Synthetic Holder", class: "8/B" },
          },
        },
      });
    }
    if (path === "/api/admin/actions/31/undo") {
      classUndone = true;
      return route.fulfill({ json: { ...created, status: "undone" } });
    }
    return route.abort();
  });
}

for (const size of [
  { width: 1440, height: 900, item: "change-row" },
  { width: 390, height: 844, item: "change-card" },
]) {
  test(`recent changes list, page and show their undo window at ${size.width}px`, async ({
    page,
  }) => {
    await page.setViewportSize(size);
    await mockApi(page);
    await page.goto(`${adminOrigin}/admin/changes`);

    const items = page.getByTestId(size.item);
    await expect(items).toHaveCount(2);
    await expect(items.first()).toContainText("Synthetic Pupil moved 8/A → 8/B");
    await expect(items.first()).toContainText(
      en.changes.statuses.available.replace("{{count}}", "3"),
    );
    // The page itself never scrolls sideways.
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);

    await page.getByRole("button", { name: en.changes.loadMore }).click();
    await expect(items).toHaveCount(3);
    await expect(items.last()).toContainText("4 fields copied");
    await expect(items.last()).toContainText(en.changes.statuses.expired);
    await expect(items.last().getByRole("button", { name: /^Undo/ })).toHaveCount(0);
  });
}

test("a refused undo names the conflict and changes nothing", async ({ page }) => {
  await mockApi(page);
  await page.goto(`${adminOrigin}/admin/changes`);

  await page.getByRole("button", { name: /^Undo: Synthetic Pupil moved/ }).click();
  const dialog = page.getByRole("dialog", { name: en.changes.confirmTitle });
  await expect(dialog).toContainText("Synthetic Pupil moved 8/A → 8/B");
  await dialog.getByRole("button", { name: en.changes.undo, exact: true }).click();

  await expect(
    page.getByText("School number 123 is now used by Synthetic Holder in 8/B."),
  ).toBeVisible();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("button", { name: /^Undo: Synthetic Pupil moved/ })).toBeVisible();
});

test("an accepted undo refreshes the list with who undid it", async ({ page }) => {
  await mockApi(page);
  await page.goto(`${adminOrigin}/admin/changes`);

  await page.getByRole("button", { name: "Undo: Class 8/C added" }).click();
  await page
    .getByRole("dialog", { name: en.changes.confirmTitle })
    .getByRole("button", { name: en.changes.undo, exact: true })
    .click();

  await expect(page.getByText(en.changes.undone)).toBeVisible();
  const row = page.getByTestId("change-row").filter({ hasText: "Class 8/C added" });
  await expect(row).toContainText("Undone — Synthetic Admin");
  await expect(row.getByRole("button", { name: /^Undo/ })).toHaveCount(0);
});

test("coordinators neither see nor open recent changes", async ({ page }) => {
  await mockApi(page, { ...admin, is_admin: false, is_coordinator: true });
  await page.goto(`${adminOrigin}/admin/changes`);
  await expect(page).toHaveURL(`${adminOrigin}/admin/`);
  const navigation = page.getByRole("navigation").first();
  await expect(navigation.getByRole("link", { name: en.changes.title })).toHaveCount(0);
});
