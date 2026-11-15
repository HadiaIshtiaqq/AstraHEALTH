import { expect, test } from "@playwright/test";

test.describe("ASTRAHEALTH crew flows", () => {
  test("overview shows status, labels and no banner clutter", async ({ page }) => {
    await page.goto("/?profile=crew-demo-02");
    await expect(page.getByText("SYNTHETIC DATA", { exact: true })).toHaveCount(0);
    await expect(page.getByText("LOCAL · OFFLINE")).toBeVisible();
    await expect(page.getByText("Qualified review recommended")).toBeVisible();
    // notifications live in the bell, not as full-width banners
    await expect(page.getByRole("region", { name: "Active alerts" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Notifications: \d+ open/ })).toBeVisible();
    await expect(page.getByText("What to improve")).toBeVisible();
  });

  test("navigation contains only crew-relevant sections", async ({ page }) => {
    await page.goto("/");
    const nav = page.getByRole("navigation", { name: "Main" }).first();
    for (const item of ["Overview", "Check-in", "Care Plan", "Health Trends", "Reports"]) {
      await expect(nav.getByRole("link", { name: item })).toBeVisible();
    }
    await expect(nav.getByRole("link", { name: "AI Agents" })).toHaveCount(0);
    await expect(nav.getByRole("link", { name: "Settings" })).toHaveCount(0);
  });

  test("manual check-in is validated, saved and analysed with a care plan", async ({ page }) => {
    await page.goto("/check-in?profile=crew-demo-01");
    await page.getByLabel("Heart rate (bpm)").fill("63");
    await page.getByLabel("Blood pressure — systolic (mmHg)").fill("118");
    await expect(page.getByText("Blood pressure requires both systolic and diastolic values").first()).toBeVisible({ timeout: 15_000 }); // debounced server validation
    await page.getByLabel("Blood pressure — diastolic (mmHg)").fill("76");
    await page.getByRole("button", { name: "Continue" }).click();
    await page.getByLabel("Sleep duration — last sleep period (hours)").fill("7.3");
    await page.getByRole("button", { name: "Continue" }).click();
    await page.getByRole("button", { name: "Continue" }).click();
    await page.getByRole("button", { name: "Submit check-in" }).click();
    await expect(page.getByText("Check-in saved and analysed")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText("How to improve this")).toBeVisible();
  });

  test("urgent alert: persistent pill, crew cannot dismiss, medical officer PIN clears it", async ({ page, request }) => {
    await request.post("/api/v1/demo/scenarios/urgent/run", { headers: { "X-Admin-PIN": "222222" } });
    await page.goto("/?profile=crew-demo-03");
    const pill = page.getByRole("button", { name: /Urgent alert active/ });
    await expect(pill).toBeVisible();
    await pill.click();
    await expect(page.getByText("Urgent: contact the medical officer")).toBeVisible(); // one notification per urgent event
    await expect(page.getByRole("button", { name: "Mark as read" })).toHaveCount(0);
    await page.getByRole("button", { name: "Medical officer" }).first().click();
    await page.getByLabel("PIN").fill("000000");
    await page.getByRole("button", { name: "Confirm" }).click();
    await expect(page.getByText(/Medical officer PIN required/)).toBeVisible();
    await page.getByLabel("PIN").fill("111111");
    await page.getByRole("button", { name: "Confirm" }).click();
    await expect(page.getByRole("dialog", { name: /Medical officer acknowledgement/ })).toHaveCount(0);
  });

  test("care plan recommendation can be added to the routine", async ({ page, request }) => {
    // independent of other tests/browsers sharing the e2e database
    await request.post("/api/v1/profiles/crew-demo-02/reset?confirm=true", { headers: { "X-Admin-PIN": "222222" } });
    await page.goto("/care-plan?profile=crew-demo-02");
    await expect(page.getByRole("heading", { name: "Protect and rebuild sleep" })).toBeVisible();
    await page.getByRole("button", { name: /Add “Protected sleep window” to my routine/ }).click();
    await expect(page.getByText(/Added to your routine for 3 day/)).toBeVisible();
    await page.goto("/countermeasures?profile=crew-demo-02");
    await expect(page.getByText("Protected sleep window (care plan)")).toBeVisible();
  });

  test("keyboard users can skip to content and reach controls", async ({ page }) => {
    await page.goto("/");
    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  });

  test("phone width has no horizontal scrolling", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 900 });
    await page.goto("/?profile=crew-demo-02");
    await expect(page.getByText("Your health, in focus.")).toBeVisible();
    const [client, scroll] = await page.evaluate(() => [document.documentElement.clientWidth, document.documentElement.scrollWidth]);
    expect(scroll).toBeLessThanOrEqual(client);
  });
});
