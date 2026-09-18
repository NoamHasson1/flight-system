import { expect, test } from "@playwright/test";

/**
 * The whole journey, once: check a flight, read the verdict, file a claim.
 *
 * Runs against a real frontend and a real backend. It needs the backend on the
 * FAKE provider, because a live flight lookup is not deterministic -- the
 * delays change as the data is corrected, and a test whose expected answer
 * depends on what an airline did last Tuesday is a test that fails for no
 * reason. The scripted scenarios are what make an end-to-end assertion
 * possible at all.
 */

const FLIGHT = "BA165";
const DATE = "2026-08-20"; // scripted: 9h late, eligible under two laws

test.describe.configure({ mode: "serial" });

test("a customer checks a flight and files a claim", async ({ page }) => {
  // --- the check ---
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Flight delayed?");

  await page.getByLabel(/flight number/i).fill(FLIGHT);
  await page.getByLabel(/date it departed/i).fill(DATE);
  await page.getByRole("button", { name: /see what you're owed/i }).click();

  // --- the verdict ---
  // Its own URL, so it survives a refresh and can be shared.
  await page.waitForURL(/\/check\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "You can claim compensation",
  );

  // The result screen deliberately does NOT list the regulations.
  await expect(page.getByText("EC261")).toHaveCount(0);
  await expect(page.getByText("UK261")).toHaveCount(0);

  const checkUrl = page.url();
  await page.reload();
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "You can claim compensation",
  );
  expect(page.url()).toBe(checkUrl);

  // --- the claim ---
  await page.getByRole("link", { name: /start my claim/i }).click();
  await page.waitForURL(/\/claim\//);

  await page.getByLabel(/your full name/i).fill("Noam Hasson");
  await page.getByLabel(/^email$/i).fill("noam@example.com");
  await page.getByLabel(/full name on the ticket/i).fill("Noam Hasson");
  await page.getByLabel(/id or passport number/i).fill("012345678");
  await page.getByRole("button", { name: /continue/i }).click();

  await expect(page.getByText(/your booking/i)).toBeVisible();
  await page.getByLabel(/booking reference/i).fill("XJ4K2P");
  await page
    .getByLabel(/what did the airline say/i)
    .fill("They said a technical fault with the aircraft.");
  await page.getByRole("button", { name: /continue/i }).click();

  await expect(page.getByText(/what did it cost you/i)).toBeVisible();
  await page.getByRole("button", { name: /add a cost/i }).click();
  await page.getByLabel(/^amount$/i).fill("180.00");
  await page.getByRole("button", { name: /continue/i }).click();

  // Reaching Documents is what creates the claim.
  await expect(page.getByText(/upload what you have/i)).toBeVisible();
  await page.getByRole("button", { name: /continue/i }).click();

  await expect(page.getByText(/check it over/i)).toBeVisible();
  await expect(page.getByText("Noam Hasson").first()).toBeVisible();
  await expect(page.getByText(/180.00 EUR/)).toBeVisible();

  await page.getByRole("button", { name: /submit my claim/i }).click();

  // --- the reference ---
  await expect(page.getByRole("heading", { name: /your claim is in/i })).toBeVisible();
  await expect(page.getByText(/^FS-\d{4}-[A-Z0-9]{6}$/)).toBeVisible();
});

test("a flight that does not exist is not a verdict", async ({ page }) => {
  // "We looked and there is no such flight" is a question, not an answer, and
  // must never render as a denial.
  await page.goto("/");
  await page.getByLabel(/flight number/i).fill("XX999");
  await page.getByLabel(/date it departed/i).fill(DATE);
  await page.getByRole("button", { name: /see what you're owed/i }).click();

  await page.waitForURL(/\/check\//);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "We couldn't find that flight",
  );
  await expect(page.getByText(/doesn't qualify/i)).toHaveCount(0);
});

test("a provider outage never becomes a denial", async ({ page }) => {
  // The most expensive bug this product could have: somebody reads "no claim",
  // closes the tab, and nobody ever finds out.
  await page.goto("/");
  await page.getByLabel(/flight number/i).fill("ERR503");
  await page.getByLabel(/date it departed/i).fill(DATE);
  await page.getByRole("button", { name: /see what you're owed/i }).click();

  await page.waitForURL(/\/check\//);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "We need to check this by hand",
  );
});

test("several matching flights are never guessed at", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel(/flight number/i).fill("FR1234");
  await page.getByLabel(/date it departed/i).fill("2026-08-14");
  await page.getByRole("button", { name: /see what you're owed/i }).click();

  await expect(page.getByText(/which flight were you on/i)).toBeVisible();
  await expect(page.getByRole("button", { name: /departing 06:00 UTC/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /departing 16:00 UTC/i })).toBeVisible();
});
