const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { homedir } = require("node:os");

const runtime = path.join(homedir(), ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright");
const pwa = path.join(__dirname, "../pwa");
const source = fs.readFileSync(path.join(pwa, "app.js"), "utf8");
const resultsScript = source.slice(source.indexOf("let shiftOperationRequest"), source.indexOf("function formatAverage("));

test("warehouse charts fit mobile and reveal only the selected warehouse failures", { skip: !fs.existsSync(runtime) }, async () => {
  const { chromium } = require(runtime);
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    const html = fs.readFileSync(path.join(pwa, "index.html"), "utf8");
    const section = html.slice(html.indexOf('<div id="shift-operation-results-content"'),
      html.indexOf('<div id="registration-admin-content"'));
    const css = fs.readFileSync(path.join(pwa, "styles.css"), "utf8");
    await page.setContent(`<style>${css}</style><main class="app-shell">${section.replace('class="hidden"', '')}</main>`);
    await page.addScriptTag({ content: `
      window.$ = (selector) => document.querySelector(selector);
      window.formatCount = String;
      window.escapeHtml = (value) => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;");
      window.localMonth = () => "2026-11";
      const payload = { warehouses: [
        { warehouse: "BUD1", succeeded: 8, failed: 1, failures: [
          { courierName: "Első futár", workDate: "2026-11-23", shiftStart: "08:00", reason: "Átfedés" },
        ] },
        { warehouse: "BUD2", succeeded: 2, failed: 1, failures: [
          { courierName: "Második futár", workDate: "2026-11-24", shiftStart: "10:00", reason: "Nincs aktív foglalás" },
        ] },
      ] };
      window.api = async (url) => {
        window.requestedUrl = url;
        return payload;
      };
      ${resultsScript}
      loadShiftOperationResults();
    ` });
    assert.equal(await page.evaluate(() => requestedUrl), "/api/coordinator/shift-operation-results?month=2026-11&operation=deletion");
    assert.equal(await page.locator(".shift-operation-ring").count(), 2);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);

    const panel = page.locator("#shift-operation-details");
    const first = page.getByRole("button", { name: /^BUD1, 8 sikeres, 1 hibás/ });
    await first.focus();
    await first.press("Enter");
    assert.match(await panel.innerText(), /Első futár[\s\S]*Átfedés/);
    assert.doesNotMatch(await panel.innerText(), /Második futár/);
    assert.equal(await page.evaluate(() => document.activeElement.id), "shift-operation-details");

    const second = page.getByRole("button", { name: /^BUD2, 2 sikeres, 1 hibás/ });
    await second.click();
    assert.match(await panel.innerText(), /Második futár[\s\S]*Nincs aktív foglalás/);
    assert.doesNotMatch(await panel.innerText(), /Első futár/);
    await second.click();
    assert.equal(await panel.isVisible(), false);
  } finally {
    await browser.close();
  }
});
