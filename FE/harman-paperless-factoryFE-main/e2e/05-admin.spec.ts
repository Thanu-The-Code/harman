import { expect, test, type Page } from "@playwright/test";
import { PASSWORD, expectClean, expectSettled, login, watch } from "./helpers";

/**
 * People & Teams (administrators): a department, a role, a quality team and a
 * person who uses them; the person signs in; then everything is removed again.
 */

const RUN = Date.now().toString(36).toUpperCase();
const DEPT = `E2E Dept ${RUN}`;
const ROLE = `E2E Inspector ${RUN}`;
const TEAM_CODE = `E2E${RUN.slice(-4)}`;
const TEAM = `E2E Team ${RUN}`;
const USERNAME = `e2e.${RUN.toLowerCase()}`;
const FULL_NAME = `E2E Person ${RUN}`;

const openTab = async (page: Page, name: string) => {
  await page.getByRole("tab", { name, exact: true }).click();
  await expectSettled(page);
};

const dialogSelect = async (page: Page, label: string, option: string | RegExp) => {
  await page.getByRole("dialog").getByRole("combobox", { name: label, exact: true }).click();
  await page.getByRole("option", { name: option }).first().click();
};

const confirm = async (page: Page) => {
  const dialog = page.getByRole("dialog");
  await dialog.locator(".confirm-btn").click();
  await expect(dialog).toBeHidden();
};

test.describe.serial("people and teams through the UI", () => {
  test("an administrator adds a department, a role and a team", async ({ page }) => {
    const w = watch(page);
    await login(page, "admin");
    await page.goto("/people-teams");
    await expectSettled(page);

    await openTab(page, "Departments");
    await page.getByRole("button", { name: "Add department" }).click();
    await page.getByRole("dialog").getByLabel("Department name").fill(DEPT);
    await confirm(page);
    await expect(page.getByText(`${DEPT} added.`)).toBeVisible();
    await expect(page.locator(".ag-row").filter({ hasText: DEPT })).toBeVisible();

    await openTab(page, "Roles");
    await page.getByRole("button", { name: "Add Role" }).click();
    const roleDialog = page.getByRole("dialog");
    await roleDialog.getByLabel("Role name").fill(ROLE);
    await roleDialog.getByLabel("Description").fill("Fills inspection records on the line");
    // a role must allow something; the first capability offered
    const first = roleDialog.getByRole("checkbox").first();
    if (!(await first.isChecked())) await first.check();
    await confirm(page);
    await expect(page.getByText(`Role ${ROLE} added.`)).toBeVisible();
    await expect(page.locator(".ag-row").filter({ hasText: ROLE })).toBeVisible();

    await openTab(page, "Teams");
    await page.getByRole("button", { name: "New team" }).click();
    const teamDialog = page.getByRole("dialog");
    await teamDialog.getByLabel("Short code").fill(TEAM_CODE.toLowerCase() + "-!"); // tidied to capitals, no symbols
    await expect(teamDialog.getByLabel("Short code")).toHaveValue(TEAM_CODE);
    await teamDialog.getByLabel("Team name").fill(TEAM);
    await teamDialog.getByLabel("What this team is responsible for").fill("End-to-end test team");
    await confirm(page);
    await expect(page.getByText(`Team ${TEAM_CODE} added.`)).toBeVisible();
    await expect(page.getByText(TEAM, { exact: true })).toBeVisible();
    expectClean(w);
  });

  test("an administrator adds a person, who can then sign in", async ({ page }) => {
    const w = watch(page);
    await login(page, "admin");
    await page.goto("/people-teams");
    await expectSettled(page);
    await page.getByRole("button", { name: "Add a person" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Full name").fill(FULL_NAME);
    await dialog.getByLabel("Username").fill(USERNAME);
    await dialog.getByLabel("Work email").fill(`${USERNAME}@harman.example`);
    await dialogSelect(page, "Quality team", new RegExp(`^${TEAM_CODE} - `));
    await dialog.getByLabel("Job title").fill("Line Inspector");
    await dialogSelect(page, "Department", DEPT);
    // a role is required, and the password must be long enough
    await dialog.getByLabel("Temporary password").fill("short");
    await expect(dialog.locator(".confirm-btn")).toBeDisabled();
    await dialog.getByLabel("Temporary password").fill(PASSWORD);
    await dialogSelect(page, "Role", ROLE);
    await confirm(page);
    await expect(page.getByText(`${FULL_NAME} added.`)).toBeVisible();

    await openTab(page, "People");
    await page.getByPlaceholder("Search people by name, email or role").fill(RUN);
    const row = page.locator(".ag-row").filter({ hasText: USERNAME });
    await expect(row).toBeVisible();
    await expect(row).toContainText(ROLE);

    // edit: a new job title
    await row.getByRole("button", { name: `Edit ${USERNAME}` }).click();
    await page.getByRole("dialog").getByLabel("Job title").fill("Senior Line Inspector");
    await confirm(page);
    await expect(page.getByText("Saved.", { exact: true })).toBeVisible();

    // the team lists them
    await openTab(page, "Teams");
    await page.getByRole("button", { name: `Open ${TEAM}` }).click();
    await expect(page.locator(".ag-row").filter({ hasText: FULL_NAME })).toContainText("Senior Line Inspector");
    await page.getByRole("button", { name: "Back" }).click();

    // they sign in, and see no administration
    await login(page, USERNAME);
    await expect(page.getByText(FULL_NAME).first()).toBeVisible();
    await expect(page.locator("nav").getByText("Roles & Permissions")).toHaveCount(0);
    expectClean(w);
  });

  test("an administrator retires the team and removes the person, role and department", async ({ page }) => {
    const w = watch(page);
    await login(page, "admin");
    await page.goto("/people-teams");
    await expectSettled(page);

    await page.getByRole("button", { name: `Open ${TEAM}` }).click();
    await page.getByRole("button", { name: "Retire" }).click();
    await page.getByRole("dialog").locator(".confirm-btn").click(); // retiring is confirmed
    await expect(page.getByText("Team retired.")).toBeVisible();
    await page.getByRole("button", { name: "Back" }).click();
    await expect(page.getByText(`${TEAM} (retired)`)).toBeVisible();

    await openTab(page, "People");
    await page.getByPlaceholder("Search people by name, email or role").fill(RUN);
    await page.getByRole("button", { name: `Delete ${USERNAME}` }).click();
    await confirm(page);
    await expect(page.getByText("Person deleted.")).toBeVisible();
    await expect(page.locator(".ag-row").filter({ hasText: USERNAME })).toHaveCount(0);

    await openTab(page, "Roles");
    await page.getByRole("button", { name: `Delete ${ROLE}` }).click();
    await confirm(page);
    await expect(page.getByText("Role deleted.")).toBeVisible();

    await openTab(page, "Departments");
    await page.getByRole("button", { name: `Delete ${DEPT}` }).click();
    await confirm(page);
    await expect(page.getByText("Department deleted.")).toBeVisible();
    await expect(page.locator(".ag-row").filter({ hasText: DEPT })).toHaveCount(0);

    // the removed person can no longer sign in
    await page.getByRole("button", { name: "Log out" }).click();
    await page.getByLabel("Username").fill(USERNAME);
    await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
    await page.getByRole("button", { name: "Log In" }).click();
    await expect(page.getByRole("alert")).toBeVisible();
    expectClean(w);
  });
});
