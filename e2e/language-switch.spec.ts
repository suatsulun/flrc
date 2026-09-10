import type { MeOut } from "@flrc/api-client";
import { expect, test } from "@playwright/test";
import { adminOrigin, teacherOrigin } from "./helpers/origins";

for (const surface of ["login", "admin"] as const) {
  test(`${surface} language control switches all locales and preserves the selection`, async ({
    page,
  }) => {
    const user: MeOut = {
      id: 1,
      full_name: "Synthetic Admin",
      email: "admin@example-school.k12.tr",
      is_admin: true,
      is_coordinator: false,
      assignments: [],
    };
    await page.addInitScript(() => {
      if (!localStorage.getItem("i18nextLng")) localStorage.setItem("i18nextLng", "en-GB");
    });
    await page.route("**/api/**", (route) => route.fulfill({ json: [] }));
    await page.route("**/api/me", (route) =>
      surface === "admin"
        ? route.fulfill({ json: user })
        : route.fulfill({ status: 401, json: { detail: "unauthenticated" } }),
    );
    await page.goto(
      surface === "admin" ? `${adminOrigin}/admin/classes` : `${teacherOrigin}/login`,
    );
    await expect(page.getByRole("radio", { name: "EN", exact: true })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    for (const [language, label] of [
      ["de", "Sprache"],
      ["fr", "Langue"],
      ["en", "Language"],
      ["tr", "Dil"],
    ]) {
      await page.getByRole("radio", { name: language.toUpperCase(), exact: true }).click();
      const control = page.getByRole("radiogroup", { name: label, exact: true });
      await expect(
        control.getByRole("radio", { name: language.toUpperCase(), exact: true }),
      ).toHaveAttribute("aria-checked", "true");
      await expect
        .poll(() => page.evaluate(() => localStorage.getItem("i18nextLng")))
        .toBe(language);
    }
    await page.reload();
    await expect(
      page
        .getByRole("radiogroup", { name: "Dil", exact: true })
        .getByRole("radio", { name: "TR", exact: true }),
    ).toHaveAttribute("aria-checked", "true");
  });
}
