import { expect, test } from "@playwright/test";
import { api, expectClean, expectSettled, login, watch } from "./helpers";

/** The dashboard's figures, the notifications (bell, page, links) and the activity log's filters. */

interface Notification {
  id: string;
  kind: string;
  subject: string;
  related_type: string | null;
  related_id: string | null;
  read: boolean;
}
type Inbox = { notifications: Notification[]; unread: number };

test.describe("dashboard, notifications and activity log", () => {
  test("the dashboard shows the person's own figures, over the chosen range", async ({ page }) => {
    const w = watch(page);
    await login(page, "r.kumar");
    await expect(page.getByText("Hi, Ravi")).toBeVisible();
    await expectSettled(page);

    const mine = await api<{ counts: { pending: number } }>(page, "api/my-approvals?tab=pending&per_page=5");
    // the innermost box holding the card's title and its caption is the card
    const pending = page.locator("div").filter({ hasText: "Pending Approvals" }).filter({ hasText: /overdue/ }).last();
    await expect(pending).toContainText(String(mine.counts.pending));
    await expect(page.getByText("Document Activity")).toBeVisible();
    await expect(page.locator("canvas").first()).toBeVisible(); // a chart is drawn

    // a longer range asks the server again
    const refetch = page.waitForRequest((r) => /\/api\/actions\/dashboard\?.*days=30/.test(r.url()));
    await page.getByRole("button", { name: /Last 7 days/ }).first().click(); // the chart's and the activity panel's
    await page.getByRole("menuitem", { name: /30 days/ }).click();
    await refetch;
    await expect(page.getByRole("button", { name: /Last 30 days/ })).toHaveCount(2); // one range for the page
    await expectSettled(page);
    expectClean(w);
  });

  test("the bell lists the newest notifications and opens what one is about", async ({ page }) => {
    const w = watch(page);
    await login(page, "r.kumar");
    const inbox = await api<Inbox>(page, "api/records/notifications/mine?limit=5");
    test.skip(inbox.notifications.length === 0, "r.kumar has no notifications");

    await page.getByRole("button", { name: "Notifications" }).click();
    const panel = page.getByRole("dialog", { name: "Notifications" });
    await expect(panel).toBeVisible();
    await expect(panel.getByText(inbox.notifications[0].subject).first()).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(panel).toBeHidden();

    // "View all" goes to the page; the first one, opened, leaves the bell for its screen
    await page.getByRole("button", { name: "Notifications" }).click();
    await panel.getByRole("button", { name: "View all" }).click();
    await expect(page).toHaveURL(/\/notifications$/);
    await expectSettled(page);
    await page.getByRole("button", { name: "Notifications" }).click();
    await panel.getByRole("button").filter({ hasText: inbox.notifications[0].subject }).first().click();
    await expect(panel).toBeHidden();
    await expectSettled(page);
    expectClean(w);
  });

  test("every kind of notification opens a working screen", async ({ page }) => {
    const w = watch(page);
    for (const user of ["r.kumar", "s.iyer", "m.shaikh"]) {
      await login(page, user);
      const inbox = await api<Inbox>(page, "api/records/notifications/mine?limit=200");
      // one of each kind and subject type
      const seen = new Set<string>();
      const samples = inbox.notifications.filter((n) => {
        const key = `${n.kind}|${n.related_type}`;
        if (!n.related_id || seen.has(key)) return false;
        seen.add(key);
        return true;
      });
      await page.goto("/notifications");
      await expectSettled(page);
      for (const n of samples) {
        await page.getByRole("button").filter({ hasText: n.subject }).first().click();
        const open = page.getByRole("button", { name: "Open", exact: true });
        if (!(await open.count())) continue; // nothing to open for this kind
        await open.click();
        await expect(page).not.toHaveURL(/\/notifications$/);
        await expectSettled(page);
        await expect(page.getByRole("alert").filter({ hasText: /not found|Could not|Something went wrong/i }), `${user}: ${n.kind} → ${page.url()}`).toHaveCount(0);
        await page.goto("/notifications");
        await expectSettled(page);
      }
    }
    expectClean(w);
  });

  test("the notifications page filters, marks read, and marks all read", async ({ page }) => {
    const w = watch(page);
    await login(page, "p.nair");
    const before = await api<Inbox>(page, "api/records/notifications/mine?limit=200");
    test.skip(before.notifications.length === 0, "p.nair has no notifications");
    await page.goto("/notifications");
    await expectSettled(page);

    // a search with no match
    await page.getByLabel("Search notifications").fill("zz-no-such-notification-zz");
    await expect(page.getByText("No notification yet")).toBeVisible();
    await page.getByLabel("Search notifications").fill("");

    const unread = before.notifications.filter((n) => !n.read);
    if (unread.length) {
      await page.getByLabel("Filter by time").selectOption("Unread");
      await expect(page.locator(".notification-row")).toHaveCount(unread.length);
      // opening one marks it read
      await page.locator(".notification-row").first().click();
      await expect.poll(async () => (await api<Inbox>(page, "api/records/notifications/mine?limit=1")).unread).toBe(before.unread - 1);
      await page.getByLabel("Filter by time").selectOption("All Time");
      if (before.unread > 1) {
        await page.getByRole("button", { name: "Mark all as read" }).click();
        await expect.poll(async () => (await api<Inbox>(page, "api/records/notifications/mine?limit=1")).unread).toBe(0);
        await expect(page.getByRole("button", { name: "Mark all as read" })).toHaveCount(0);
        await expect(page.getByRole("button", { name: "Notifications" }).locator(".badge")).toHaveCount(0);
      }
    }
    expectClean(w);
  });

  test("the activity log filters by module and by search", async ({ page }) => {
    const w = watch(page);
    await login(page, "admin");
    await page.goto("/activity-log");
    await expectSettled(page);
    await expect(page.locator(".ag-row").first()).toBeVisible();

    const { modules } = await api<{ modules: string[] }>(page, "api/audit/modules");
    const module = modules.includes("Change Request") ? "Change Request" : modules[0];
    const filtered = page.waitForResponse((r) => r.url().includes("/api/audit?") && r.url().includes("module="));
    await page.getByLabel("Filter by module").selectOption(module);
    const body = await (await filtered).json();
    expect(body.events.every((e: { module: string }) => e.module === module)).toBe(true);
    await expectSettled(page);

    await page.getByLabel("Search by person, action or document").fill("zz-nothing-matches-zz");
    await expect(page.getByText("No activity found")).toBeVisible();
    expectClean(w);
  });
});
