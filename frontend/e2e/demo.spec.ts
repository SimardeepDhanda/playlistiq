import { expect, test } from "@playwright/test";

test("demo flow: pick a playlist, filter by artist, preview", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Demo mode")).toBeVisible();
  await page.getByRole("link", { name: "Try the demo" }).click();

  await expect(page.getByRole("heading", { name: "Your playlists" })).toBeVisible();
  await page.getByRole("link", { name: /Late Night Rotation/ }).click();

  await page.getByPlaceholder("Search artists").fill("Marlo");
  await page.getByRole("button", { name: "Include Marlo Vance", exact: true }).click();
  await page.getByRole("button", { name: "Generate preview" }).click();

  // One artist only: balanced mode cannot separate them and must say so.
  await expect(page.getByTestId("status")).toHaveText("Spacing not fully met");
  await expect(page.getByTestId("notes")).toContainText("artist variety cannot be increased");
  const count = Number((await page.getByTestId("match-count").textContent())?.replace(/,/g, ""));
  expect(count).toBeGreaterThan(100);
  await expect(page.getByTestId("rules")).toContainText("Marlo Vance");
  const rows = page.getByTestId("queue").locator("li");
  await expect(rows.first()).toContainText("Marlo Vance");
  await expect(page.getByRole("button", { name: "Export to Spotify" })).toBeDisabled();
});

test("typed request with exclusion never shows the excluded album", async ({ page }) => {
  await page.goto("/playlist/demo-late-night");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Describe what you want").fill("Marlo Vance except Overlook, random order, seed 4");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByText("Applied.")).toBeVisible();
  await page.getByRole("button", { name: "Generate preview" }).click();

  await expect(page.getByTestId("rules")).toContainText("Remove songs from: Overlook");
  await page.getByRole("button", { name: /Show more/ }).click();
  const queue = await page.getByTestId("queue").innerText();
  expect(queue).toContain("Marlo Vance");
  expect(queue).not.toMatch(/· Overlook/);
});

test("three artists with spacing meets every rule", async ({ page }) => {
  await page.goto("/playlist/demo-late-night");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Describe what you want").fill("Kiro, Lumen Hart and Nia Solstice, no same artist back to back");
  await page.getByRole("button", { name: "Apply" }).click();
  await page.getByRole("button", { name: "Generate preview" }).click();
  await expect(page.getByTestId("status")).toHaveText("All rules met");
});

test("ambiguous name asks the user to choose", async ({ page }) => {
  await page.goto("/playlist/demo-late-night");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Describe what you want").fill("only Echo");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByText('More than one artist called "Echo"')).toBeVisible();
});

test("single-artist playlist in strict balanced mode reports infeasible", async ({ page }) => {
  await page.goto("/playlist/demo-calder-deep-dive");
  await page.waitForLoadState("networkidle");
  await page.getByLabel(/Strict/).check();
  await page.getByRole("button", { name: "Generate preview" }).click();
  await expect(page.getByTestId("status")).toHaveText("Impossible with these rules");
  await expect(page.getByTestId("notes")).toContainText("artist variety cannot be increased");
});
