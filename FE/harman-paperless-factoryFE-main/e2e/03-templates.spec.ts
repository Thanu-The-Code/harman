import { expect, test, type Page } from "@playwright/test";
import path from "node:path";
import { api, expectClean, expectSettled, login, watch } from "./helpers";

/**
 * Process step 1 through the screens (Figma: Template builder / Document create):
 * an administrator designs a template on the canvas (Field Properties, a Table / Grid
 * with limits per cell), names and files it in Create Template, sets the responsibilities
 * (Continue) and sends it for approval; the QMS Coordinator releases it; the Process
 * Owner fills a record of it. Upload File turns an Excel workbook and a scanned PDF
 * into templates through the OCR service.
 */

const SHOTS = process.env.E2E_SHOTS;
const shot = async (page: Page, name: string) => {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
};

// the client's sample forms, kept with the backend's OCR tests (run from the frontend folder)
const SAMPLES = path.resolve(process.cwd(), "../../BE/tests/ocr/samples/client");
const RUN = Date.now().toString(36).toUpperCase();
const CODE = `E2E-TPL-${RUN}`;
const TITLE = "E2E torque and run-out check";
let formatId = "";

/** A MUI select: open it by its label, pick the option. */
const choose = async (page: Page, label: string, option: RegExp) => {
  await page.getByRole("combobox", { name: label, exact: true }).click();
  await page.getByRole("option", { name: option }).first().click();
};

const card = (page: Page, element: string) => page.locator(`.designer-sheet .rfb-card[data-element="${element}"]`);
const properties = (page: Page) => page.locator(".designer-panel .field-properties");

/** Create Template: title, code, team and a folder of the library. */
const fillDetails = async (page: Page, title: string, code: string, folder: string) => {
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Create Template")).toBeVisible();
  await dialog.getByLabel("Form title").fill(title);
  await dialog.getByLabel("Form code").fill(code);
  await choose(page, "Quality team", /^PQ - /);
  await dialog.getByLabel("Find a folder").fill(folder);
  await dialog.getByRole("treeitem", { name: new RegExp(folder) }).click();
  await expect(dialog.getByLabel("Folder path")).toContainText(`Teams / Process Quality / ${folder}`);
  await dialog.getByRole("button", { name: "Create", exact: true }).click();
};

test.describe.serial("template designer through the UI", () => {
  test("an administrator designs a template and sends it for approval", async ({ page }) => {
    const w = watch(page);
    await login(page, "admin");
    await page.goto("/builder");
    await expectSettled(page);
    await expect(page.getByRole("tab", { name: "Pending Approval" })).toBeVisible();
    await page.getByRole("button", { name: "New Template" }).click();
    await expect(page).toHaveURL(/\/builder\/new\/build$/);
    await expect(page.locator("header h1")).toHaveText("Template builder / Document create");
    await expect(page.getByRole("heading", { name: "Untitled" })).toBeVisible();

    // two fields from the palette
    const palette = page.locator(".rfb-tiles");
    await palette.getByText("Number Input", { exact: true }).click();
    await palette.getByText("Table/Grid", { exact: true }).click();
    await expect(card(page, "NumberInput")).toHaveCount(1);
    await expect(card(page, "Table")).toHaveCount(1);
    await expect(page.locator(".rfb-tiles i, .rfb-tiles svg").first()).toBeVisible();

    // the number: label, limits, required (Field Properties)
    await card(page, "NumberInput").click();
    await expect(page.getByRole("tab", { name: "Field Properties" })).toHaveAttribute("aria-selected", "true");
    await expect(properties(page)).toContainText("Number Input Field");
    await properties(page).getByLabel("Field label").fill("Line pressure");
    await properties(page).getByLabel("Minimum").fill("10");
    await properties(page).getByLabel("Maximum").fill("20");
    await properties(page).getByLabel("Unit").fill("bar");
    await properties(page).getByLabel("Required field").check();
    await expect(card(page, "NumberInput")).toContainText("Line pressure");

    // the table: printed check points, a reading with limits, a ✓ / ✗ cell
    await card(page, "Table").click();
    await expect(properties(page)).toContainText("Table/Grid Field");
    const editor = properties(page).locator(".table-editor");
    const body = editor.locator("tbody tr");
    await body.nth(0).locator("textarea").first().fill("Bolt torque");
    await body.nth(1).locator("textarea").first().fill("Run-out");
    await body.nth(0).locator("td.te-input").first().click();
    await editor.getByLabel("Cell minimum").fill("20");
    await editor.getByLabel("Cell maximum").fill("25");
    await editor.getByLabel("Cell unit").fill("Nm");
    await body.nth(1).locator("td.te-input").first().click();
    await editor.getByLabel("Cell minimum").fill("0");
    await editor.getByLabel("Cell maximum").fill("0.05");
    await editor.getByLabel("Cell unit").fill("mm");
    await properties(page).getByRole("button", { name: "Done" }).click();
    await expect(card(page, "Table")).toContainText("Bolt torque");
    await shot(page, "designer-filled");

    // Save Draft: the template has no name yet, so Create Template asks for it
    await page.getByRole("button", { name: "Save Draft" }).click();
    await fillDetails(page, TITLE, CODE, "Procedures");
    await expect(page.getByText("Template created as a draft.")).toBeVisible();
    await expect(page).toHaveURL(/\/builder\/[0-9a-f-]{36}\/build\?format_id=/);
    formatId = new URL(page.url()).searchParams.get("format_id")!;
    await expect(page.getByRole("heading", { name: TITLE })).toBeVisible();
    await expect(card(page, "Table")).toContainText("Run-out"); // reopened from the server

    // the server derived one field per recorded thing: the number + 2 rows x (reading, tick)
    type Saved = { field_count: number; storage_path: string | null; readiness: string[]; fields: { label: string; spec_min: number | null; spec_max: number | null; spec_text: string | null; required: boolean }[] };
    const saved = await api<Saved>(page, `api/formats/${formatId}`);
    expect(saved.field_count).toBe(5);
    expect(saved.storage_path).toBe("Teams / Process Quality / Procedures");
    expect(saved.fields.map((f) => [f.spec_min, f.spec_max])).toEqual(expect.arrayContaining([[10, 20], [20, 25], [0, 0.05]]));
    expect(saved.fields.find((f) => f.label === "Line pressure")?.required).toBe(true);
    expect(saved.fields.filter((f) => f.spec_text === "OK")).toHaveLength(2); // the ✓ / ✗ cells

    // Continue: who fills and approves, then send for approval
    await page.getByRole("button", { name: "Continue" }).click();
    await expect(page).toHaveURL(/step=process/);
    await expect(page.getByText("What this template records")).toBeVisible();
    await choose(page, "Process Owner", /Ravi Kumar/);
    await choose(page, "Overall Process Owner", /Sunita Iyer/);
    await choose(page, "QMS Coordinator", /Mohammed Shaikh/);
    const cft = page.getByRole("combobox", { name: "Quality CFT members" });
    for (const name of ["Priya Nair", "Anil Deshmukh"]) {
      await cft.click();
      await cft.fill(name.split(" ")[0]);
      await page.getByRole("option", { name: new RegExp(name) }).click();
    }
    await page.getByLabel("Work instruction", { exact: true }).fill("Torque each bolt, then measure run-out.");
    await shot(page, "designer-process");
    await page.getByRole("button", { name: "Send for approval" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText("Mohammed Shaikh")).toBeVisible();
    await dialog.locator(".confirm-btn").click();
    await expect(page.getByText("Sent for approval. The reviewers have been notified.")).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`/builder/${formatId}$`));
    await expectSettled(page);
    await expect(page.getByText("5 recorded entries")).toBeVisible();
    expectClean(w);
  });

  test("the QMS Coordinator reviews it from My Approvals and releases it", async ({ page }) => {
    const w = watch(page);
    await login(page, "m.shaikh");
    await page.goto("/my-approvals");
    await page.getByRole("tab", { name: /Template approvals/ }).click();
    const row = page.locator(".ag-row").filter({ hasText: CODE });
    await expect(row).toBeVisible();
    await row.getByRole("button", { name: `Review ${CODE}` }).click();
    await expect(page).toHaveURL(new RegExp(`/builder/${formatId}$`));
    await expectSettled(page);
    await expect(page.getByText("Your review is requested")).toBeVisible();
    await page.locator(".action-buttons").getByRole("button", { name: "Approve", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("textbox").first().fill("Limits match the drawing");
    await dialog.locator(".confirm-btn").click();
    await expect(page.getByText("Approved. The template is now released.")).toBeVisible();
    expectClean(w);
  });

  test("the Process Owner files a record of it; the table is filled and judged", async ({ page }) => {
    const w = watch(page);
    await login(page, "r.kumar");
    await page.goto(`/resources?format=${formatId}`);
    await expectSettled(page);
    await expect(page.locator(".preview-title")).toHaveText(TITLE);
    await page.getByRole("button", { name: "File", exact: true }).click();
    await expect(page).toHaveURL(/\/my-forms\/[0-9a-f-]{36}$/);
    await expectSettled(page);

    await expect(page.getByText("Torque each bolt, then measure run-out.")).toBeVisible();
    const table = page.locator(".record-table");
    const rows = table.locator("tbody tr");
    await expect(rows).toHaveCount(2);
    await expect(rows.first()).toContainText("Bolt torque");
    await rows.nth(0).locator('input[type="number"]').fill("22.5");
    await rows.nth(1).locator('input[type="number"]').fill("0.09"); // run-out too high
    await expect(rows.nth(0).locator(".spec-badge.ok")).toBeVisible();
    await expect(rows.nth(1).locator(".spec-badge.nok")).toBeVisible();
    // the tick cell: a native ✓ / ✗ select (a check sheet has hundreds of them)
    await rows.nth(0).locator("select").selectOption("OK");
    const pressure = page.locator(".value-field").filter({ hasText: "Line pressure" });
    await pressure.getByRole("spinbutton").fill("15");
    await expect(pressure.locator(".spec-badge.ok")).toBeVisible();

    await expect(page.locator(".save-state")).toContainText(/Saved/, { timeout: 15_000 });
    await expect(page.getByText(/outside specification/)).toBeVisible();
    await shot(page, "layout-record");
    await page.reload();
    await expectSettled(page);
    await expect(page.locator(".record-table tbody tr").nth(1).locator('input[type="number"]')).toHaveValue("0.09");
    expectClean(w);
  });

  test("Upload File: an Excel check sheet becomes a template", async ({ page }) => {
    const w = watch(page);
    await login(page, "admin");
    await page.goto("/builder");
    await page.getByRole("button", { name: "Upload File" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText("Create a template from a document")).toBeVisible();
    await expect(dialog.getByText(/Supported: .*Excel/)).toBeVisible();
    await dialog.getByLabel("Document to convert").setInputFiles(path.join(SAMPLES, "IFC Check Sheet.xlsx"));
    await dialog.getByRole("button", { name: "Convert" }).click();
    await expect(dialog.getByText(/Detected .*table/)).toBeVisible({ timeout: 60_000 });
    await shot(page, "upload-detected");
    await dialog.getByRole("button", { name: "Open in designer" }).click();

    await expect(page).toHaveURL(/\/builder\/new\/build$/);
    await expect(card(page, "Table")).toHaveCount(1);
    // Create Template opens straight away, with the sheet's title
    const details = page.getByRole("dialog");
    await expect(details.getByLabel("Form title")).not.toHaveValue("");
    await fillDetails(page, `E2E IFC check sheet ${RUN}`, `E2E-XLS-${RUN}`, "Inspection Logs");
    await expect(page.getByRole("heading", { name: `E2E IFC check sheet ${RUN}` })).toBeVisible();
    await page.getByRole("button", { name: "Save Draft" }).click();
    await expect(page.getByText("Template created as a draft.")).toBeVisible();
    const id = new URL(page.url()).searchParams.get("format_id")!;
    const saved = await api<{ field_count: number; readiness: string[] }>(page, `api/formats/${id}`);
    expect(saved.field_count).toBeGreaterThan(100); // a column per day of the month
    expect(saved.readiness).toEqual([]);
    expectClean(w);
  });

  test("Upload File: a scanned PDF is read with OCR into a template", async ({ page }) => {
    test.setTimeout(300_000);
    const w = watch(page);
    await login(page, "admin");
    const formats = await api<{ ocr_available: boolean }>(page, "api/ocr/formats");
    test.skip(!formats.ocr_available, "the server has no OCR engine (requirements-ocr.txt)");
    await page.goto("/builder");
    await page.getByRole("button", { name: "Upload File" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Document to convert").setInputFiles(path.join(SAMPLES, "HPU-F-MR-04_Document _Creation_Change Request.pdf"));
    await dialog.getByRole("button", { name: "Convert" }).click();
    await expect(dialog.getByRole("status")).toContainText("Reading the document");
    await expect(dialog.getByText(/Detected /)).toBeVisible({ timeout: 240_000 });
    // a scan is shown with what was found outlined on it
    await expect(dialog.locator(".ocr-page-image")).toBeVisible();
    await shot(page, "upload-scan-detected");
    await dialog.getByRole("button", { name: "Open in designer" }).click();
    await expect(page).toHaveURL(/\/builder\/new\/build$/);
    await expect(page.locator(".designer-sheet .rfb-card").first()).toBeVisible();
    expect(await page.locator(".designer-sheet .rfb-card").count()).toBeGreaterThan(5);
    expectClean(w);
  });
});
