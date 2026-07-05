import { test, expect } from "@playwright/test";

// ============================================================
// StockInsight Pro — E2E 回归测试
// 覆盖 5 条关键用户路径（无需登录）
// ============================================================

test.describe("基本 UI 加载", () => {
  test("首页仪表盘加载", async ({ page }) => {
    await page.goto("/");

    // 等待导航栏渲染
    await expect(page.locator(".nav-logo")).toBeVisible({ timeout: 15000 });
    await expect(page.locator(".nav-logo")).toContainText("Stock");

    // 验证标签页
    await expect(page.locator(".nav-tab").first()).toContainText("仪表盘");
    await expect(page.locator(".nav-tab").nth(1)).toContainText("持仓");
    await expect(page.locator(".nav-tab").nth(2)).toContainText("设置");
  });

  test("侧边栏自选股加载", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".sidebar")).toBeVisible({ timeout: 15000 });
    await expect(page.locator(".wl-item").first()).toBeVisible();
  });
});

test.describe("搜索功能", () => {
  test("搜索框输入股票代码", async ({ page }) => {
    await page.goto("/");

    // 输入股票代码
    const searchInput = page.locator(".nav-search");
    await expect(searchInput).toBeVisible({ timeout: 15000 });
    await searchInput.fill("600519");

    // 点击分析按钮
    await page.locator(".nav-btn.primary").click();

    // 验证跳转
    await expect(page).toHaveURL(/\/stock\/600519/);
  });
});

test.describe("页面路由", () => {
  test("导航到持仓页", async ({ page }) => {
    await page.goto("/");

    // 点击"持仓"标签
    await page.locator(".nav-tab").nth(1).click();
    await expect(page).toHaveURL(/\/portfolio/);
  });

  test("导航到设置页", async ({ page }) => {
    await page.goto("/");

    // 点击"设置"标签
    await page.locator(".nav-tab").nth(2).click();
    await expect(page).toHaveURL(/\/settings/);
  });
});

test.describe("侧边栏交互", () => {
  test("点击自选股导航到个股分析", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".wl-item").first()).toBeVisible({ timeout: 15000 });

    // 点击第一个自选股
    await page.locator(".wl-item").first().click();
    await expect(page).toHaveURL(/\/stock\/\d{6}/);
  });
});

test.describe("页面内容完整性", () => {
  test("底部声明可见", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".footer")).toBeVisible({ timeout: 15000 });
    await expect(page.locator(".footer")).toContainText("免责声明");
  });

  test("API 健康检查启动提示", async ({ page }) => {
    await page.goto("/");

    // 检查加载状态（API 可能未就绪，显示启动提示）
    await page.waitForTimeout(3000);
    const body = page.locator("body");
    const bodyText = await body.textContent();
    expect(
      bodyText.includes("正在启动") || bodyText.includes("仪表盘")
    ).toBeTruthy();
  });
});
