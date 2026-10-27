import { expect, test, type Page } from "@playwright/test";
import { api, expectClean, expectSettled, login, sign, watch } from "./helpers";

/**
 * The record process (Project Core Workflow.pdf) driven through the screens:
 * fill → PO approval → OPO (clears the N-OK flag) → CFT joint review (one
 * objection) → final decision "No" → CFT again → final "Yes" → filed.
 */

const SHOTS = process.env.E2E_SHOTS; // folder for screenshots worth looking at
const shot = async (page: Page, name: string) => {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
};

let recordId = "";
let recordNumber = "";

const openReview = async (page: Page) => {
  await page.goto(`/my-approvals/${recordId}`);
  await expectSettled(page);
  await expect(page.getByText(recordNumber).first()).toBeVisible();
};

/** Answer the current step from the review page. */
const answer = async (page: Page, button: string, opts: { note?: string; signature?: boolean } = {}) => {
  await page.locator(".action-buttons").getByRole("button", { name: button, exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  if (opts.note) await dialog.getByRole("textbox").first().fill(opts.note);
  if (opts.signature) await sign(page);
  await dialog.locator(".confirm-btn").click();
  await expect(dialog).toBeHidden();
  await expectSettled(page);
};

test.describe.serial("record process through the UI", () => {
  test("Process Owner fills the record: live OK / N-OK, auto-save, evidence", async ({ page }) => {
    const w = watch(page);
    await login(page, "r.kumar");
    // a fresh record each run (a second record for the period is allowed), so the suite repeats
    const formats = await api<{ formats: { id: string; code: string }[] }>(page, "api/formats/callable");
    const qf = formats.formats.find((f) => f.code === "QF-PQ-001")!;
    recordNumber = (await api<{ number: string }>(page, "api/records/call", { method: "POST", body: { format_id: qf.id } })).number;

    await page.goto("/my-forms");
    await page.getByRole("tab", { name: /^Draft/ }).click();
    await page.getByPlaceholder(/record number/).fill(recordNumber);
    const row = page.locator(".ag-row").filter({ hasText: recordNumber });
    await expect(row).toHaveCount(1);
    await row.getByRole("button", { name: /^Open / }).click();
    await expect(page).toHaveURL(/\/my-forms\/[0-9a-f-]{36}$/);
    recordId = page.url().split("/").pop()!;
    await expectSettled(page);
    await expect(page.getByText("Work instruction")).toBeVisible();

    // an out-of-spec bore diameter turns N-OK while typing
    const bore = page.getByLabel("Bore diameter", { exact: true });
    await bore.fill("25.34");
    const boreField = page.locator(".value-field").filter({ has: bore });
    await expect(boreField.locator(".spec-badge.nok")).toBeVisible();
    await expect(boreField.getByPlaceholder(/Remark/)).toBeVisible();
    await boreField.getByPlaceholder(/Remark/).fill("Tool wear, part quarantined");
    await page.getByLabel("Surface finish", { exact: true }).fill("1.2");
    await page.getByLabel("Run-out", { exact: true }).fill("0.03");
    await page.getByLabel("Gauge serial", { exact: true }).fill("BG-0417");
    await expect(page.locator(".value-field").filter({ has: page.getByLabel("Run-out", { exact: true }) }).locator(".spec-badge.ok")).toBeVisible();

    // auto-save, then the server's verdict: N-OK banner
    await expect(page.locator(".save-state")).toContainText(/Saved/, { timeout: 15_000 });
    await expect(page.getByText(/outside specification/)).toBeVisible();

    // a supporting file
    await page.getByPlaceholder("Caption (optional)").fill("Gauge certificate");
    const chooser = page.waitForEvent("filechooser");
    await page.getByRole("button", { name: "Add file" }).click();
    await (await chooser).setFiles({ name: "gauge-cert.txt", mimeType: "text/plain", buffer: Buffer.from(`calibrated ${Date.now()}`) });
    await expect(page.getByRole("button", { name: "gauge-cert.txt", exact: true }).first()).toBeVisible();
    await shot(page, "fill-page");

    // reload: everything was saved
    await page.reload();
    await expectSettled(page);
    await expect(page.getByLabel("Bore diameter", { exact: true })).toHaveValue("25.34");
    await expect(page.getByLabel("Gauge serial", { exact: true })).toHaveValue("BG-0417");
    expectClean(w);
  });

  test("Process Owner confirms the approvers and submits", async ({ page }) => {
    const w = watch(page);
    await login(page, "r.kumar");
    await page.goto(`/my-forms/${recordId}`);
    await page.getByRole("button", { name: "Set up Approval" }).click();
    await expect(page).toHaveURL(new RegExp(`/my-forms/${recordId}/approval$`));
    await expectSettled(page);
    await expect(page.getByText("Ravi Kumar").first()).toBeVisible();
    await expect(page.getByText("Sunita Iyer").first()).toBeVisible();
    await expect(page.getByText(/flagged to the Overall Process Owner/)).toBeVisible();
    await shot(page, "approval-setup");
    await page.getByRole("button", { name: "Start Approval" }).click();
    await expect(page.getByText("Approval process started!")).toBeVisible();
    await page.getByRole("button", { name: "Done" }).click();
    await expect(page).toHaveURL(/\/my-forms$/);

    // My Documents: on verification, red
    await expect(page.locator(".ag-row").filter({ hasText: recordNumber })).toBeVisible();

    // Track status: step 1 in progress with Ravi Kumar
    await page.goto(`/my-forms/${recordId}?tab=track`);
    await expectSettled(page);
    await expect(page.getByText("Approval Timeline")).toBeVisible();
    await expect(page.locator(".timeline-item").first()).toContainText("In Progress");
    await shot(page, "track-status");
    expectClean(w);
  });

  test("Process Owner approves and signs from My Approvals", async ({ page }) => {
    const w = watch(page);
    await login(page, "r.kumar");
    await page.goto("/my-approvals");
    await expectSettled(page);
    const row = page.locator(".ag-row").filter({ hasText: "In-process dimensional check" }).first();
    await expect(row).toBeVisible();
    // the document preview is the PDF stamped with the signatures so far
    const stamped = page.waitForResponse((r) => /\/api\/signatures\/[^/]+\/preview$/.test(r.url()));
    await openReview(page);
    const pdf = await stamped;
    expect(pdf.status()).toBe(200);
    expect(pdf.headers()["content-type"]).toContain("application/pdf");
    await expect(page.getByText(/N-OK flagged/)).toBeVisible();
    await expect(page.locator(".readings-table tr.nok")).toHaveCount(1);
    await shot(page, "review-po");

    // a signed step cannot be confirmed without a signature
    await page.locator(".action-buttons").getByRole("button", { name: "Approve", exact: true }).click();
    await expect(page.getByRole("dialog").locator(".confirm-btn")).toBeDisabled();
    await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();

    await answer(page, "Approve", { note: "Within condition apart from the bore", signature: true });
    await expect(page.getByText("No action needed from you")).toBeVisible();
    expectClean(w);
  });

  test("Overall Process Owner clears the N-OK flag and approves", async ({ page }) => {
    const w = watch(page);
    await login(page, "s.iyer");
    await openReview(page);
    await answer(page, "Clear N-OK flag", { note: "Lot quarantined, bore re-machined" });
    await expect(page.getByText(/N-OK flagged/)).toHaveCount(0);
    await answer(page, "Approve", { signature: true });
    await expect(page.getByText(/CFT joint review/).first()).toBeVisible();
    expectClean(w);
  });

  test("Quality CFT: one objects, one agrees", async ({ page }) => {
    const w = watch(page);
    await login(page, "a.deshmukh");
    await openReview(page);
    await answer(page, "Object", { note: "Bore trend needs a second look" });
    await login(page, "p.nair");
    await openReview(page);
    await expect(page.getByText(/CFT objection/)).toBeVisible();
    await answer(page, "Agree");
    expectClean(w);
  });

  test("Final decision sends it back; the CFT re-agrees; final approval", async ({ page }) => {
    const w = watch(page);
    await login(page, "r.kumar");
    await openReview(page);
    await answer(page, "Send back to CFT", { note: "Re-verify the bore with the CFT" });
    await expect(page.getByText(/re-verification 1/)).toBeVisible();

    for (const member of ["a.deshmukh", "p.nair"]) {
      await login(page, member);
      await openReview(page);
      await answer(page, "Agree");
    }
    await login(page, "r.kumar");
    await openReview(page);
    await answer(page, "Approve", { signature: true });
    expectClean(w);
  });

  test("Overall Process Owner files it; it is in the Doc Repository", async ({ page }) => {
    const w = watch(page);
    await login(page, "s.iyer");
    await openReview(page);
    await answer(page, "File record");
    await expect(page.getByText(/Filed/).first()).toBeVisible();

    await page.goto("/doc-repo");
    await expectSettled(page);
    await page.getByPlaceholder(/Search by record number/).fill(recordNumber);
    const row = page.locator("tr").filter({ hasText: recordNumber });
    await expect(row).toBeVisible();
    await row.getByRole("button", { name: /^Open / }).click();
    await expectSettled(page);
    await expect(page.getByText("Record Summary")).toBeVisible();
    await expect(page.locator(".readings-table tbody tr")).toHaveCount(5);
    await expect(page.getByText(/Signed by Ravi Kumar/).first()).toBeVisible();
    await shot(page, "repository-detail");
    expectClean(w);
  });
});
