import { expect, test } from "@playwright/test";
import { expectClean, expectSettled, login, watch } from "./helpers";

/** Every screen a person can open loads, settles and shows its real data. */

// path, something the page itself shows, the header's title
const EVERYONE: [string, RegExp, string][] = [
  ["/", /Hi,/, "Dashboard"],
  ["/resources", /Released formats/, "Resources Library"],
  ["/my-forms", /On Verification/, "My Documents"],
  ["/my-approvals", /Pending Approval/, "My Approvals"],
  ["/doc-repo", /Document Repository/, "Doc Repository"],
  ["/request", /Format changes/, "Change Request"],
  ["/activity-log", /Every recorded action/, "Activity Log"],
  ["/notifications", /Approval requests, N-OK flags/, "Notification"],
  ["/settings", /Profile Setting/, "Settings"],
];

const ADMIN_ONLY: [string, RegExp, string][] = [
  ["/builder", /Create and manage reusable templates/, "Template Builder"],
  ["/builder-repo", /Every template and its revisions/, "Template Repository"],
  ["/people-teams", /Manage people, teams, roles/, "Roles & Permissions"],
];

test.describe("every screen loads", () => {
  for (const user of ["admin", "r.kumar", "s.iyer", "p.nair", "m.shaikh"]) {
    test(`as ${user}`, async ({ page }) => {
      const w = watch(page);
      await login(page, user);
      const screens = user === "admin" ? [...EVERYONE, ...ADMIN_ONLY] : EVERYONE;
      for (const [path, content, title] of screens) {
        await page.goto(path);
        await expect(page.getByText(content).first(), `${path} content`).toBeVisible();
        await expect(page.locator("header h1").first(), `${path} header title`).toHaveText(title);
        await expectSettled(page);
      }
      expectClean(w);
    });
  }

  test("admin screens are hidden and guarded for others", async ({ page }) => {
    const w = watch(page);
    await login(page, "r.kumar");
    const nav = page.locator("nav");
    await expect(nav.getByText("Template Builder")).toHaveCount(0);
    await expect(nav.getByText("Roles & Permissions")).toHaveCount(0);
    for (const path of ["/builder", "/people-teams", "/builder-repo"]) {
      await page.goto(path);
      // told why, not dropped on the dashboard without a word
      await expect(page.getByRole("alert")).toContainText("This screen is for administrators");
    }
    expectClean(w);
  });

  test("the header shows who is signed in, and logout works", async ({ page }) => {
    await login(page, "s.iyer");
    await expect(page.getByText("Sunita Iyer").first()).toBeVisible();
    await page.getByRole("button", { name: "Log out" }).click();
    await expect(page).toHaveURL(/\/login/);
    await page.goto("/my-forms");
    await expect(page).toHaveURL(/\/login/);
  });

  test("a wrong password is refused", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Username").fill("r.kumar");
    await page.getByLabel("Password", { exact: true }).fill("nope-nope");
    await page.getByRole("button", { name: "Log In" }).click();
    await expect(page.getByRole("alert")).toContainText("Incorrect username or password");
  });
});
