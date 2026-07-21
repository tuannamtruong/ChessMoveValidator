// Frontend smoke test: serve frontend/ statically, drive it with a headless
// Chromium (Playwright), take a screenshot, and assert the UI contract still
// holds. This is the browser-facing backward-compatibility check — the form
// must render and the "API not configured" path (the state of the tracked,
// placeholder config.js) must surface a clear error rather than silently break.
//
// Run: node tests/smoke_frontend.mjs   (from the repo root)
// Screenshot lands at tests/screenshots/frontend.png
import { chromium } from "playwright";
import http from "node:http";
import { readFile, mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const frontendDir = path.join(root, "frontend");
const shotDir = path.join(here, "screenshots");

const MIME = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
};

const server = http.createServer(async (req, res) => {
  let rel = decodeURIComponent(req.url.split("?")[0]);
  if (rel === "/") rel = "/index.html";
  try {
    const buf = await readFile(path.join(frontendDir, rel));
    res.writeHead(200, {
      "Content-Type": MIME[path.extname(rel)] || "application/octet-stream",
    });
    res.end(buf);
  } catch {
    res.writeHead(404);
    res.end("not found");
  }
});

const checks = [];
const check = (name, cond) => {
  checks.push([name, !!cond]);
};

await new Promise((r) => server.listen(0, r));
const base = `http://127.0.0.1:${server.address().port}`;

const browser = await chromium.launch();
let failed = false;
try {
  const page = await browser.newPage({ viewport: { width: 900, height: 900 } });
  const consoleErrors = [];
  page.on("pageerror", (e) => consoleErrors.push(String(e)));
  await page.goto(base, { waitUntil: "networkidle" });

  check(
    "title is Chess Move Validator",
    (await page.title()) === "Chess Move Validator",
  );
  check(
    "heading rendered",
    await page.locator("h1", { hasText: "Chess Move Validator" }).isVisible(),
  );
  check("email input present", await page.locator("#email").isVisible());
  check("file picker present", await page.locator(".file-picker").isVisible());
  check("submit button present", await page.locator("#submit").isVisible());
  check("no uncaught page errors on load", consoleErrors.length === 0);

  // Selecting a file updates the filename label (pure client behavior).
  await page.setInputFiles("#file", {
    name: "game.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("e2e4 e7e5"),
  });
  check(
    "file name label updates on select",
    (await page.locator("#file-name").textContent()) === "game.txt",
  );

  // Backward-compat: with the placeholder config.js (UPLOAD_API_URL === ''),
  // submitting must show the configured-service error, not hang or throw.
  await page.fill("#email", "player@example.com");
  await page.click("#submit");
  await page.waitForSelector("#status:not([hidden])", { timeout: 5000 });
  const statusText = (await page.locator("#status").textContent()) || "";
  check(
    "unconfigured API surfaces an error status",
    /not configured/i.test(statusText),
  );
  check(
    "status uses the error style",
    (await page.locator("#status").getAttribute("class")).includes("error"),
  );

  await mkdir(shotDir, { recursive: true });
  await page.screenshot({
    path: path.join(shotDir, "frontend.png"),
    fullPage: true,
  });
} finally {
  await browser.close();
  server.close();
}

console.log("Frontend smoke test:");
for (const [name, ok] of checks) {
  console.log(`  ${ok ? "ok  " : "FAIL"} ${name}`);
  if (!ok) failed = true;
}
console.log(`  screenshot: tests/screenshots/frontend.png`);
const passed = checks.filter(([, ok]) => ok).length;
console.log(`\n${passed} passed, ${checks.length - passed} failed`);
process.exit(failed ? 1 : 0);
