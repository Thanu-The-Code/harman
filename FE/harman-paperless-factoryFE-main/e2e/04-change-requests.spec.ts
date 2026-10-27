import { expect, test, type Page } from "@playwright/test";
import { api, expectClean, expectSettled, login, watch } from "./helpers";

/**
 * Change requests through the screens: a format change (DCR) approved by the
 * QMS Coordinator and executed into a draft, one turned down, and a change to
 * a filled record (RCR) decided and implemented.
 */

const RUN = Date.now().toString(36).toUpperCase();
const NEW_CODE = `E2E-NEW-${RUN}`;
const newDcr = { id: "", number: "" };
const rcr = { id: "", number: "" };

/** A MUI select inside the open dialog. */
const choose = async (page: Page, label: string, option: RegExp) => {
  await page.getByRole("dialog").getByRole("combobox", { name: label, exact: true }).click();
  await page.getByRole("option", { name: option }).first().click();
};

/** The number in a "<number> raised …" toast. */
const raisedNumber = async (page: Page, prefix: string) => {
  const toast = page.locator(".Toastify__toast").filter({ hasText: /raised/ }).last();
  await expect(toast).toBeVisible();
  return (await toast.innerText()).match(new RegExp(`${prefix}[\\w-]+`))![0];
};

/** Find a request in the list (search, then the eye button) and open it. */
const openFromList = async (page: Page, number: string, kind: "dcr" | "rcr") => {
  await page.goto(kind === "rcr" ? "/request?type=rcr" : "/request");
  await expectSettled(page);
  await page.getByPlaceholder("Find by title, number or code").fill(number);
  if (kind === "dcr") {
    // the DCR list is one status tab at a time; find the tab it is in
    for (const tab of ["Submitted", "Under review", "Approved", "Executed", "Not approved"]) {
      await page.getByRole("tab", { name: tab, exact: true }).click();
      if (await page.locator(".ag-row").filter({ hasText: number }).count()) break;
    }
  }
  const row = page.locator(".ag-row").filter({ hasText: number });
  await expect(row).toHaveCount(1);
  await row.getByRole("button", { name: "View change request" }).click();
  await expect(page).toHaveURL(new RegExp(`/change-request/${kind}/[0-9a-f-]{36}$`));
  await expectSettled(page);
  return page.url().split("/").pop()!;
};

/** A decision dialog: optional note, then confirm. */
const confirmDialog = async (page: Page, note?: string) => {
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  if (note) await dialog.getByRole("textbox").first().fill(note);
  await dialog.locator(".confirm-btn").click();
  await expect(dialog).toBeHidden();
};

test.describe.serial("change requests through the UI", () => {
  test("a Process Owner asks for a new format", async ({ page }) => {
    const w = watch(page);
    await login(page, "r.kumar");
    await page.goto("/request");
    await expectSettled(page);
    await page.getByRole("button", { name: "New change request" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText("Raise a change request")).toBeVisible();
    await choose(page, "What is needed", /A new format/);
    await choose(page, "Quality team", /^PQ - /);
    await choose(page, "QMS Coordinator", /Mohammed Shaikh/);
    await dialog.getByLabel("Title").fill(`E2E coolant concentration log ${RUN}`);
    await dialog.getByLabel("Why is a change needed?").fill("Coolant is checked on paper only.");
    await dialog.getByLabel("What the new format must record").fill("Concentration % per machine, twice a shift.");
    await dialog.locator(".confirm-btn").click();
    newDcr.number = await raisedNumber(page, "DCR");
    await expect(page.locator(".Toastify__toast").last()).toContainText("Mohammed Shaikh");
    expectClean(w);
  });

  test("the QMS Coordinator reviews, approves and creates the format", async ({ page }) => {
    const w = watch(page);
    await login(page, "m.shaikh");
    await page.goto("/request");
    await page.getByText(/Waiting on me/).click();
    newDcr.id = await openFromList(page, newDcr.number, "dcr");
    await expect(page.getByText("Concentration % per machine, twice a shift.")).toBeVisible();

    await page.getByRole("button", { name: "Start review" }).click();
    await expect(page.getByText("Marked as under review.")).toBeVisible();
    await page.getByRole("button", { name: "Approved", exact: true }).click();
    await confirmDialog(page, "Agreed — needed for the coolant audit");
    await expect(page.getByText("Approved. The raiser and Process Owner are notified.")).toBeVisible();

    await page.getByRole("button", { name: "Create the new format" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Form code").fill(NEW_CODE);
    await dialog.locator(".confirm-btn").click();
    await expect(page.getByText(`${NEW_CODE} rev 00 created as a draft.`)).toBeVisible();
    await expect(page.getByText(new RegExp(`${NEW_CODE} rev 00 \\(draft\\)`))).toBeVisible();
    expectClean(w);
  });

  test("an administrator opens the resulting draft in the designer", async ({ page }) => {
    const w = watch(page);
    await login(page, "admin");
    await page.goto(`/change-request/dcr/${newDcr.id}`);
    await expectSettled(page);
    await page.getByRole("button", { name: "Open the draft in the designer" }).click();
    await expect(page).toHaveURL(/\/builder\/[0-9a-f-]{36}\/build\?format_id=/);
    // Document create: the requested title, the new code beside it, and the canvas to draw it on
    await expect(page.getByRole("heading", { name: `E2E coolant concentration log ${RUN}` })).toBeVisible();
    await expect(page.locator(".designer-title")).toContainText(`${NEW_CODE} · rev 00`);
    await expect(page.locator(".rfb-tiles")).toBeVisible();
    await page.getByRole("button", { name: "Edit", exact: true }).click();
    await expect(page.getByRole("dialog").getByLabel("Form code")).toHaveValue(NEW_CODE);
    await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();
    expectClean(w);
  });

  test("a change to a released format, raised from Resources, is turned down", async ({ page }) => {
    const w = watch(page);
    await login(page, "r.kumar");
    // a format of r.kumar's with no change already open against it (only one may be open at a time)
    const formats = await api<{ formats: { id: string; code: string }[] }>(page, "api/formats/callable");
    const open = new Set<string>();
    for (const status of ["submitted", "under_review", "approved"]) {
      const list = await api<{ requests: { format: { id: string } | null }[] }>(page, `api/change-requests?status=${status}`);
      list.requests.forEach((r) => r.format && open.add(r.format.id));
    }
    const target = formats.formats.find((f) => !open.has(f.id));
    expect(target, "a released format with no open change request").toBeTruthy();

    const raise = async () => {
      await page.goto(`/resources?format=${target!.id}`);
      await expectSettled(page);
      await page.getByRole("button", { name: "Change Request", exact: true }).click();
      const dialog = page.getByRole("dialog");
      await expect(dialog.getByText(new RegExp(`For ${target!.code}`))).toBeVisible();
      await dialog.getByLabel("Title").fill(`E2E widen tolerance ${RUN}`);
      await dialog.getByLabel("Why is a change needed?").fill("Customer drawing rev C allows ±0.15.");
      await dialog.getByLabel("Proposed change").fill("Widen the limit to ±0.15");
      await dialog.locator(".confirm-btn").click();
    };
    await raise();
    const number = await raisedNumber(page, "DCR");
    // a second one against the same format is refused, and the reason is shown
    await raise();
    await expect(page.locator(".Toastify__toast").filter({ hasText: `${number} is already open against ${target!.code}` })).toBeVisible();
    await expect(page.getByRole("dialog")).toBeVisible(); // nothing typed is lost

    await login(page, "m.shaikh");
    await openFromList(page, number, "dcr");
    await page.getByRole("button", { name: "Not Approved", exact: true }).click();
    // a refusal needs a reason
    await expect(page.getByRole("dialog").locator(".confirm-btn")).toBeDisabled();
    await confirmDialog(page, "Drawing rev C is not yet released to production");
    await expect(page.getByText("Marked as not approved.")).toBeVisible();
    await expect(page.getByText("Drawing rev C is not yet released to production")).toBeVisible();
    expectClean(w);
  });

  test("a record change: raised on the record, approved, implemented", async ({ page }) => {
    const w = watch(page);
    await login(page, "r.kumar");
    type Item = { id: string; number: string; stage: string; can: { request_change: boolean } };
    const listing = await api<{ items: Item[] }>(page, "api/records/documents-listing?tab=verification&page_size=50");
    const submitted = listing.items.filter((i) => i.stage !== "filling");

    // a record r.kumar only reviews offers no change request
    const reviewOnly = submitted.find((i) => !i.can.request_change);
    if (reviewOnly) {
      await page.goto(`/my-forms/${reviewOnly.id}`);
      await expectSettled(page);
      await expect(page.getByText(reviewOnly.number).first()).toBeVisible();
      await expect(page.getByRole("button", { name: "Request a change" })).toHaveCount(0);
    }

    // one of their own, with no change request already open on it
    const open = await api<{ requests: { record: { id: string } | null }[] }>(page, "api/record-change-requests?status=open");
    const busy = new Set(open.requests.map((r) => r.record?.id));
    const record = submitted.find((i) => i.can.request_change && !busy.has(i.id))!;
    expect(record, "a submitted record r.kumar may change").toBeTruthy();
    await page.goto(`/my-forms/${record.id}`);
    await expectSettled(page);
    await page.getByRole("button", { name: "Request a change" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText(record.number)).toBeVisible();
    await dialog.getByLabel("Title").fill(`E2E correct gauge serial ${RUN}`);
    await dialog.getByLabel("What has to change, and why?").fill("Gauge serial was typed as BG-0471; it is BG-0417.");
    await dialog.locator(".confirm-btn").click();
    rcr.number = await raisedNumber(page, "RCR");

    await login(page, "m.shaikh");
    rcr.id = await openFromList(page, rcr.number, "rcr");
    await expect(page.getByText(record.number).first()).toBeVisible();
    await page.getByRole("button", { name: "Approved", exact: true }).click();
    await confirmDialog(page, "Correct it and note the source");
    await expect(page.getByText("Approved.", { exact: true })).toBeVisible();

    await login(page, "r.kumar");
    await page.goto(`/change-request/rcr/${rcr.id}`);
    await expectSettled(page);
    await page.getByRole("button", { name: "Mark implemented" }).click();
    await confirmDialog(page, "Serial corrected from the calibration register");
    await expect(page.getByText("Marked as implemented.")).toBeVisible();
    await expect(page.getByText("Serial corrected from the calibration register")).toBeVisible();
    await expect(page.locator(".cr-footer")).toContainText("Implemented");
    expectClean(w);
  });
});
