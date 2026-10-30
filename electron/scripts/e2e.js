// End-to-end test of the Electron app: drives the real app window with
// Playwright, the way a user would.
//   node scripts/e2e.js [--exe <installed app .exe>] [--out <dir>] [--scenario <file.js>] ...
// Without --exe it starts the shell from this checkout (npx electron .).
//
// It first opens every page in the app's navigation and fails on any Python
// exception shown on a page. Each --scenario module then gets the helpers
// below to run app-specific steps, e.g. a workflow and its viewer:
//   module.exports = async (t) => { await t.open("Workflow"); ... }
const fs = require("fs");
const path = require("path");

function loadPlaywright() {
  for (const name of ["playwright-core", "playwright"]) {
    try {
      return require(name);
    } catch (_) {}
  }
  throw new Error("Playwright is missing: run `npm ci` in electron/ (playwright-core is a devDependency)");
}

function parseArgs(argv) {
  const args = { scenarios: [], out: path.resolve("e2e-output") };
  for (let i = 0; i < argv.length; i++) {
    const key = argv[i];
    const value = argv[++i];
    if (key === "--exe") args.exe = path.resolve(value);
    else if (key === "--out") args.out = path.resolve(value);
    else if (key === "--scenario") args.scenarios.push(path.resolve(value));
    else throw new Error(`unknown argument ${key}`);
  }
  return args;
}

async function launch(_electron, exe) {
  const env = { ...process.env };
  // The installed app must not run its own smoke test or update dialog here.
  delete env.OPENMS_APP_SMOKE_TEST;
  env.OPENMS_APP_NO_UPDATE_CHECK = "1";
  if (exe) return _electron.launch({ executablePath: exe, env, timeout: 120000 });
  const electronDir = path.resolve(__dirname, "..");
  const args = [electronDir];
  if (process.platform === "linux") args.unshift("--no-sandbox");
  return _electron.launch({ executablePath: require("electron"), args, env, timeout: 120000 });
}

// Streamlit marks its root element with the script state; "notRunning" for a
// while means the page has finished rendering (fragments may still poll).
async function settle(page, { timeout = 120000, quiet = 1500 } = {}) {
  const started = Date.now();
  let idleSince = null;
  while (Date.now() - started < timeout) {
    const state = await page
      .locator('[data-testid="stApp"]')
      .first()
      .getAttribute("data-test-script-state")
      .catch(() => null);
    if (state === "notRunning") {
      idleSince = idleSince || Date.now();
      if (Date.now() - idleSince >= quiet) return;
    } else {
      idleSince = null;
    }
    await page.waitForTimeout(250);
  }
  throw new Error(`page did not finish running within ${timeout / 1000}s: ${page.url()}`);
}

async function exceptions(page) {
  return page.locator('[data-testid="stException"]').allInnerTexts();
}

function makeHelpers(app, page, baseUrl, out) {
  let shots = 0;
  const t = {
    app,
    page,
    baseUrl,
    out,
    log: (...msg) => console.log("  ", ...msg),
    settle: (opts) => settle(page, opts),

    // Open a page by its URL path ("FLASHDeconvWorkflow") or by a title from
    // the navigation ("Workflow"); a title shared by several sections needs
    // the URL path.
    async open(target) {
      await expandNav(page);
      const link = page.locator(`[data-testid="stSidebarNav"] a[href$="/${target}"]`);
      if ((await link.count()) === 1) await link.click();
      else await page.locator('[data-testid="stSidebarNav"] a', { hasText: target }).first().click();
      await settle(page);
    },

    async clickTab(name) {
      await page.getByRole("tab", { name }).first().click();
      await settle(page);
    },

    async clickButton(name) {
      await page.getByRole("button", { name }).first().click();
      await settle(page);
    },

    // Picks an option in the st.multiselect or st.selectbox with this label.
    async choose(label, option) {
      const widget = page
        .locator('[data-testid="stMultiSelect"], [data-testid="stSelectbox"]')
        .filter({ has: page.locator('[data-testid="stWidgetLabel"]', { hasText: label }) })
        .first();
      const multi = (await widget.getAttribute("data-testid")) === "stMultiSelect";
      // Typing into the search box opens the list and narrows it. A click on
      // the box can land on a chip already picked, which opens nothing.
      const search = widget.locator("input").first();
      await search.click();
      await search.fill(option);
      await page.getByRole("option", { name: option }).first().click();
      // A multiselect stays open after a pick. Escape on a selectbox would
      // clear the value just chosen.
      if (multi) await page.keyboard.press("Escape");
      await settle(page);
    },

    // Waits until a custom component frame matches `selector`; returns it.
    async waitForComponent(selector, { timeout = 180000 } = {}) {
      const started = Date.now();
      while (Date.now() - started < timeout) {
        for (const frame of t.componentFrames()) {
          if ((await frame.locator(selector).count().catch(() => 0)) > 0) return frame;
        }
        await t.assertNoException();
        await page.waitForTimeout(1000);
      }
      throw new Error(`no component frame shows ${selector} within ${timeout / 1000}s`);
    },

    // Waits for text anywhere on the page, failing early on an exception.
    async waitForText(text, { timeout = 600000, failOn = [] } = {}) {
      const started = Date.now();
      while (Date.now() - started < timeout) {
        const body = await page.locator("body").innerText().catch(() => "");
        const bad = failOn.find((f) => body.includes(f));
        if (bad) throw new Error(`"${bad}" shown while waiting for "${text}"`);
        const exc = await exceptions(page);
        if (exc.length) throw new Error(`exception while waiting for "${text}":\n${exc.join("\n")}`);
        if (body.includes(text)) return;
        await page.waitForTimeout(1000);
      }
      throw new Error(`"${text}" did not appear within ${timeout / 1000}s`);
    },

    async assertNoException(where) {
      const exc = await exceptions(page);
      if (exc.length) throw new Error(`exception on ${where || page.url()}:\n${exc.join("\n")}`);
    },

    // Frames of Streamlit custom components (Vue component, OpenMS-Insight, ...).
    componentFrames() {
      return page.frames().filter((f) => f !== page.mainFrame() && /\/component\//.test(f.url()));
    },

    async shot(name) {
      const file = path.join(out, `${String(++shots).padStart(2, "0")}-${name.replace(/[^\w.-]+/g, "_")}.png`);
      await page.screenshot({ path: file, fullPage: true });
      return file;
    },
  };
  return t;
}

// A long navigation is collapsed behind "View more"; links past it are only
// in the page once it is expanded.
async function expandNav(page) {
  const more = page.locator('[data-testid="stSidebarNavViewButton"]');
  if ((await more.count()) && /more/i.test(await more.first().innerText())) {
    await more.first().click();
    await settle(page);
  }
}

async function navTargets(page) {
  await expandNav(page);
  const hrefs = await page
    .locator('[data-testid="stSidebarNav"] a')
    .evaluateAll((as) => as.map((a) => a.getAttribute("href")));
  return [...new Set(hrefs.map((h) => new URL(h, "http://x").pathname.replace(/^\//, "")))];
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  fs.mkdirSync(args.out, { recursive: true });
  const { _electron } = loadPlaywright();
  const app = await launch(_electron, args.exe);
  let failed = false;
  try {
    const page = await app.firstWindow();
    page.on("console", (m) => {
      if (m.type() === "error") console.log(`   [console] ${m.text()}`);
    });
    await page.waitForURL(/^http:\/\/127\.0\.0\.1:\d+\//, { timeout: 300000 });
    const baseUrl = new URL(page.url()).origin;
    console.log(`App is up at ${baseUrl}`);
    await settle(page);
    const t = makeHelpers(app, page, baseUrl, args.out);

    const pages = await navTargets(page);
    console.log(`Opening ${pages.length} pages`);
    for (const target of pages) {
      await t.open(target);
      await t.shot(`page-${target || "home"}`);
      await t.assertNoException(target || "home");
      console.log(`ok: page ${target || "home"}`);
    }

    for (const scenario of args.scenarios) {
      console.log(`Scenario ${path.basename(scenario)}`);
      try {
        await require(scenario)(t);
        await t.assertNoException(path.basename(scenario));
        console.log(`ok: scenario ${path.basename(scenario)}`);
      } catch (err) {
        failed = true;
        await t.shot(`failed-${path.basename(scenario)}`).catch(() => {});
        console.error(`FAILED: scenario ${path.basename(scenario)}: ${err.stack || err}`);
      }
    }
  } finally {
    await app.close().catch(() => {});
  }
  if (failed) throw new Error("one or more scenarios failed");
}

main().then(
  () => process.exit(0),
  (err) => {
    console.error(err.stack || err.message);
    process.exit(1);
  }
);
