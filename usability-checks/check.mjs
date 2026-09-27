// Playwright usability sweep for one running OpenMS Streamlit app.
//
// Opens every page listed in the sidebar navigation, once per workspace, and
// records what a user would hit: Python exceptions rendered by Streamlit,
// st.error boxes, uncaught browser errors, pages that never finish running.
// Every page gets a full-page screenshot.
//
// usage: node check.mjs --app NAME --url http://localhost:8601 --out DIR
//          [--workspace NAME]... [--example-workflow] [--live]
import { createRequire } from "node:module";
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const require = createRequire(import.meta.url);
let playwright;
try {
  playwright = require("playwright");
} catch {
  const globalRoot = execSync("npm root -g").toString().trim();
  playwright = require(path.join(globalRoot, "playwright"));
}

const args = { workspace: [] };
for (let i = 2; i < process.argv.length; i++) {
  const a = process.argv[i].replace(/^--/, "");
  if (a === "example-workflow" || a === "live") args[a] = true;
  else if (a === "workspace") args.workspace.push(process.argv[++i]);
  else args[a] = process.argv[++i];
}
if (!args.workspace.length) args.workspace.push(null);

const EXPECTED_ERRORS = /TOPP tool '[^']+' not found|No results to show yet/i;
const RUN_TIMEOUT = Number(process.env.PAGE_TIMEOUT_MS || 120000);
// Third-party noise that says nothing about the app.
const CONSOLE_IGNORE = /matomo|piwik|googletagmanager|google-analytics|favicon|ERR_TUNNEL_CONNECTION_FAILED|ERR_CONNECTION|net::ERR_|Failed to load resource/i;

fs.mkdirSync(path.join(args.out, "screenshots"), { recursive: true });
const results = { app: args.app, url: args.url, live: !!args.live, started: new Date().toISOString(), pages: [], scenarios: [] };

const browser = await playwright.chromium.launch();

function withWorkspace(url, ws) {
  const u = new URL(url);
  if (ws) u.searchParams.set("workspace", ws);
  return u.toString();
}

// Wait until the Streamlit script run is over: stApp reports
// data-test-script-state="notRunning" and stays there for a moment.
async function waitForIdle(page) {
  await page.waitForSelector('[data-testid="stApp"]', { timeout: RUN_TIMEOUT });
  const deadline = Date.now() + RUN_TIMEOUT;
  let quietSince = null;
  while (Date.now() < deadline) {
    const state = await page
      .locator('[data-testid="stApp"]')
      .first()
      .getAttribute("data-test-script-state")
      .catch(() => null);
    if (state === "notRunning") {
      quietSince ??= Date.now();
      if (Date.now() - quietSince > 1500) return true;
    } else quietSince = null;
    await page.waitForTimeout(250);
  }
  return false;
}

async function inspect(page) {
  // Keep the head (error message) and the tail (the app frame that raised it).
  const clip = (t) => (t.length > 1200 ? `${t.slice(0, 400)} ... ${t.slice(-800)}` : t);
  const texts = async (sel) =>
    (await page.locator(sel).allInnerTexts()).map((t) => clip(t.trim())).filter(Boolean);
  return {
    exceptions: await texts('[data-testid="stException"]'),
    errors: await texts('[data-testid="stAlertContentError"]'),
    warnings: await texts('[data-testid="stAlertContentWarning"]'),
    notFound: await page.getByText("Page not found", { exact: false }).count(),
    title: (await texts("h1")).at(0) || "",
  };
}

function slug(s) {
  return s.replace(/[^a-z0-9]+/gi, "_").replace(/^_|_$/g, "").slice(0, 80);
}

async function newPage() {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  const browserErrors = [];
  page.on("pageerror", (e) => browserErrors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() === "error" && !CONSOLE_IGNORE.test(m.text())) browserErrors.push(`console: ${m.text().slice(0, 400)}`);
  });
  return { context, page, browserErrors };
}

async function visit(page, browserErrors, url, label) {
  browserErrors.length = 0;
  const t0 = Date.now();
  let loadError = null;
  let idle = false;
  try {
    const resp = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
    if (resp && resp.status() >= 400) loadError = `HTTP ${resp.status()}`;
    idle = await waitForIdle(page);
  } catch (e) {
    loadError = e.message.split("\n")[0];
  }
  const found = loadError ? { exceptions: [], errors: [], warnings: [], notFound: 0, title: "" } : await inspect(page);
  const shot = path.join("screenshots", `${slug(label)}.png`);
  await page.screenshot({ path: path.join(args.out, shot), fullPage: true }).catch(() => {});
  const failures = [];
  if (loadError) failures.push(`did not load: ${loadError}`);
  if (!loadError && !idle) failures.push(`still running after ${RUN_TIMEOUT / 1000}s`);
  if (found.notFound) failures.push("Streamlit 'Page not found'");
  for (const e of found.exceptions) failures.push(`exception: ${e}`);
  for (const e of browserErrors) if (e.startsWith("pageerror")) failures.push(e);
  // Messages that describe this container (no TOPP binaries) or an empty
  // workspace rather than a defect; reported once per app as notes.
  const topp = found.errors.map((e) => e.match(/TOPP tool '([^']+)' not found/)).filter(Boolean).map((m) => m[1]);
  const errors = found.errors.filter((e) => !EXPECTED_ERRORS.test(e));
  const warnings = [
    ...errors.map((e) => `st.error: ${e}`),
    ...browserErrors.filter((e) => e.startsWith("console")),
  ];
  return { label, url, missingTopp: topp, seconds: +((Date.now() - t0) / 1000).toFixed(1), title: found.title, failures, warnings, screenshot: shot };
}

// Collect every page link in the sidebar navigation, expanding "View more".
async function navLinks(page) {
  const more = page.locator('[data-testid="stSidebarNavViewButton"]');
  if (await more.count()) {
    const txt = (await more.first().innerText()).toLowerCase();
    if (txt.includes("more")) await more.first().click().catch(() => {});
    await page.waitForTimeout(300);
  }
  const links = await page.locator('[data-testid="stSidebarNav"] a[data-testid="stSidebarNavLink"]').evaluateAll((as) =>
    as.map((a) => {
      // Link text is "<icon>\n<title>"; section headers precede each page group.
      const text = a.innerText.trim().split("\n").pop().trim();
      const hdr = a.closest("li")?.parentElement?.querySelector('[data-testid="stNavSectionHeader"]');
      const sec = hdr ? hdr.innerText.trim().split("\n")[0] : "";
      return { href: a.href, text, section: sec };
    }),
  );
  const seen = new Set();
  return links.filter((l) => !seen.has(l.href) && seen.add(l.href));
}

for (const ws of args.workspace) {
  const wsLabel = !ws ? "fresh" : /demo/.test(ws) ? "demo" : "fresh";
  const { context, page, browserErrors } = await newPage();
  const home = await visit(page, browserErrors, withWorkspace(args.url, ws), `${wsLabel}__home`);
  home.workspace = wsLabel;
  results.pages.push(home);
  let links = [];
  try {
    links = await navLinks(page);
  } catch {}
  if (!links.length && !home.failures.length) {
    home.warnings.push(args.live ? "no page navigation visible (captcha / consent gate?)" : "no sidebar navigation found");
  }
  for (const l of links) {
    const u = new URL(l.href);
    if (u.pathname === new URL(args.url).pathname || u.pathname === "/") continue; // home, already visited
    const label = `${wsLabel}__${l.section ? l.section + "_" : ""}${l.text}`;
    const r = await visit(page, browserErrors, withWorkspace(l.href, ws), label);
    r.workspace = wsLabel;
    r.page = `${l.section ? l.section + " / " : ""}${l.text}`;
    results.pages.push(r);
  }
  await context.close();
}

// Template's pyOpenMS example: File Upload loads the example mzML files into an
// empty workspace, then "Run Workflow" reads them and reports spectrum counts.
if (args["example-workflow"] && !args.live) {
  const ws = args.workspace.find((w) => w && !/demo/.test(w)) || args.workspace[0];
  const { context, page, browserErrors } = await newPage();
  const base = new URL(args.url).origin;
  const scen = { name: "example mzML workflow", failures: [], warnings: [] };
  const up = await visit(page, browserErrors, withWorkspace(`${base}/file_upload`, ws), "scenario__file_upload");
  scen.failures.push(...up.failures);
  const run = await visit(page, browserErrors, withWorkspace(`${base}/run_example_workflow`, ws), "scenario__run_example_workflow_before");
  scen.failures.push(...run.failures);
  try {
    const ms = page.locator('[data-testid="stMultiSelect"]').first();
    await ms.click();
    for (let i = 0; i < 10; i++) {
      const opt = page.locator('[role="option"]').first();
      if (!(await opt.count())) break;
      await opt.click();
      await page.waitForTimeout(200);
    }
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Run Workflow" }).click();
    await page.waitForTimeout(1000);
    if (!(await waitForIdle(page))) scen.failures.push("workflow still running after timeout");
    const found = await inspect(page);
    scen.failures.push(...found.exceptions.map((e) => `exception: ${e}`));
    scen.warnings.push(...found.errors.map((e) => `st.error: ${e}`), ...found.warnings.map((e) => `st.warning: ${e}`));
    const tables = await page.locator('[data-testid="stDataFrame"], [data-testid="stTable"], .js-plotly-plot').count();
    if (!tables) scen.failures.push("no result table or plot shown after running the workflow");
  } catch (e) {
    scen.failures.push(`could not drive the workflow: ${e.message.split("\n")[0]}`);
  }
  scen.screenshot = "screenshots/scenario__run_example_workflow_after.png";
  await page.screenshot({ path: path.join(args.out, scen.screenshot), fullPage: true }).catch(() => {});
  results.scenarios.push(scen);
  await context.close();
}

await browser.close();
results.finished = new Date().toISOString();
results.failed = results.pages.filter((p) => p.failures.length).length + results.scenarios.filter((s) => s.failures.length).length;
fs.writeFileSync(path.join(args.out, "results.json"), JSON.stringify(results, null, 2));
console.log(`${args.app}: ${results.pages.length} pages, ${results.scenarios.length} scenarios, ${results.failed} failing`);
