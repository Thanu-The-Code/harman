import { expect, type Page } from "@playwright/test";

export const PASSWORD = "Harman@2026";

/** Problems seen while a test ran: uncaught errors, console errors, server failures. */
export interface Watch {
  problems: string[];
}

/** Collect anything that means the screen is broken, whatever the test asserts. */
export const watch = (page: Page): Watch => {
  const w: Watch = { problems: [] };
  page.on("pageerror", (e) => w.problems.push(`page error: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() !== "error") return;
    const text = m.text();
    // expected noise: a 4xx the screen handles (shown as a message), React dev hints
    if (/status of 4\d\d|Download the React DevTools/.test(text)) return;
    w.problems.push(`console: ${text}`);
  });
  page.on("response", (r) => {
    if (r.url().includes("/api/") && r.status() >= 500) w.problems.push(`HTTP ${r.status()} ${r.request().method()} ${r.url()}`);
  });
  return w;
};

export const expectClean = (w: Watch) => expect(w.problems, w.problems.join("\n")).toEqual([]);

export const login = async (page: Page, username: string) => {
  await page.goto("/login");
  await page.evaluate(() => localStorage.clear());
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Log In" }).click();
  await expect(page).not.toHaveURL(/\/login/);
  await expect(page.locator("header").getByText(/./).first()).toBeVisible();
};

/** No error panel, no endless spinner. */
export const expectSettled = async (page: Page) => {
  await expect(page.getByRole("status").filter({ hasText: /Loading|Signing you in/ })).toHaveCount(0, { timeout: 20_000 });
  await expect(page.getByRole("alert").filter({ hasText: /Could not|not found|Something went wrong/i })).toHaveCount(0);
};

/** The API, as the signed-in browser sees it (bearer from localStorage). */
export const api = async <T>(page: Page, path: string, init: { method?: string; body?: unknown } = {}): Promise<T> => {
  return page.evaluate(
    async ({ path, init }) => {
      const res = await fetch(`/${path.replace(/^\//, "")}`, {
        method: init.method ?? "GET",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${localStorage.getItem("token")}` },
        body: init.body === undefined ? undefined : JSON.stringify(init.body),
      });
      const text = await res.text();
      if (!res.ok) throw new Error(`${res.status} ${path}: ${text.slice(0, 300)}`);
      return text ? JSON.parse(text) : null;
    },
    { path, init },
  ) as Promise<T>;
};

/** Draw a short stroke on the signature pad. */
export const sign = async (page: Page) => {
  const pad = page.getByRole("img", { name: /Signature area/ });
  await expect(pad).toBeVisible();
  const box = (await pad.boundingBox())!;
  await page.mouse.move(box.x + 30, box.y + 60);
  await page.mouse.down();
  for (let i = 1; i <= 12; i++) await page.mouse.move(box.x + 30 + i * 18, box.y + 60 + (i % 2 ? 25 : -20));
  await page.mouse.up();
};
