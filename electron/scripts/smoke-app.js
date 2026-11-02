// CI smoke test of the installed app: starts it with OPENMS_APP_SMOKE_TEST=1,
// which makes the shell exit 0 once the page has created a workspace, and
// prints the shell's Streamlit log afterwards.
//   node scripts/smoke-app.js <app executable> [<log file>] [--timeout <seconds>]
// On Linux run it under xvfb-run.
const fs = require("fs");
const { spawn } = require("child_process");

const args = process.argv.slice(2);
let timeout = 300;
const i = args.indexOf("--timeout");
if (i >= 0) timeout = Number(args.splice(i, 2)[1]);
const [exe, log] = args;
if (!exe) {
  console.error("usage: smoke-app.js <app executable> [<log file>] [--timeout <seconds>]");
  process.exit(2);
}

const env = { ...process.env, OPENMS_APP_SMOKE_TEST: "1", OPENMS_APP_NO_UPDATE_CHECK: "1" };
const child = spawn(exe, [], { env, stdio: "inherit" });

const timer = setTimeout(() => {
  console.error(`::error::the app did not finish its smoke test within ${timeout} s`);
  child.kill("SIGKILL");
}, timeout * 1000);

function finish(code) {
  clearTimeout(timer);
  if (log && fs.existsSync(log)) process.stdout.write(fs.readFileSync(log, "utf8"));
  process.exit(code);
}

child.on("error", (err) => {
  console.error(`::error::could not start ${exe}: ${err.message}`);
  finish(1);
});
child.on("exit", (code, signal) => {
  if (code !== 0) console.error(`::error::app smoke test failed (exit code ${code}${signal ? `, ${signal}` : ""})`);
  finish(code === null ? 1 : code);
});
