// The screen shown while the bundled Streamlit server starts: the OpenMS logo
// assembling itself, its spectrum bars rising from the baseline and then
// moving like a live acquisition until the app is ready. The screen is an
// overlay over the window: the app page loads beneath it, and only once
// APP_READY_SCRIPT says Streamlit has drawn the page does FINISH_SCRIPT play
// the bars back into the logo and fade the overlay out.
const fs = require("fs");
const path = require("path");

// The OpenMS logo (OpenMS/Assets, logos/FinalLogo_Nov2024_Versions-01.svg):
// its spectrum bars as [x, y, width, height], the lower ones hanging from the
// baseline, the upper ones (y < BASELINE) standing on it ...
const BASELINE = 302.49;
const BARS = [
  [44.08, 302.49, 22.66, 72.54],
  [81.49, 302.49, 22.66, 107.23],
  [118.9, 302.49, 22.66, 162.9],
  [156.3, 302.49, 22.66, 84.77],
  [250.91, 302.49, 22.66, 46.45],
  [288.31, 302.49, 22.66, 133.17],
  [325.72, 302.49, 22.66, 66.86],
  [408.1, 302.49, 22.66, 92.91],
  [445.51, 302.49, 22.66, 122.17],
  [482.92, 302.49, 22.66, 151.52],
  [576.69, 199.46, 22.66, 103.03],
  [614.1, 262.66, 22.66, 39.83],
  [676.84, 199.46, 22.66, 103.03],
  [714.25, 145.15, 22.66, 157.33],
  [751.66, 235.51, 22.66, 66.98],
  [789.07, 262.66, 22.66, 39.83],
];

// ... and the letters O, p, e, n, M, S, each drawn by two paths.
const GLYPHS = [
  [
    "m38.31,208.47c0-39.2,29.98-68.41,70.72-68.41s70.52,29.02,70.52,68.41-30.17,68.41-70.52,68.41c-40.74-.01-70.72-29.22-70.72-68.41Zm127.02,0c0-32.09-24.02-55.73-56.3-55.73s-56.69,23.64-56.69,55.73,24.21,55.73,56.69,55.73c32.28-.01,56.3-23.65,56.3-55.73Z",
    "m109.03,282.82c-21.23,0-40.68-7.53-54.77-21.19-14.11-13.68-21.89-32.56-21.89-53.16s7.77-39.49,21.89-53.17c14.09-13.66,33.54-21.18,54.77-21.18,43.59,0,76.46,31.96,76.46,74.35s-32.87,74.35-76.46,74.35Zm0-136.82c-37.54,0-64.78,26.27-64.78,62.47s27.24,62.46,64.78,62.47c17.99,0,34.42-6.31,46.26-17.76,11.81-11.43,18.32-27.31,18.32-44.71s-6.51-33.28-18.32-44.71c-11.84-11.45-28.27-17.76-46.26-17.76Zm0,124.14c-35.71,0-62.63-26.51-62.63-61.67s26.93-61.67,62.63-61.67,62.24,26.51,62.24,61.67-26.76,61.66-62.24,61.67Zm0-111.46c-29.41,0-50.75,20.94-50.75,49.79s21.34,49.79,50.75,49.79c29.18,0,50.36-20.95,50.36-49.79s-21.18-49.79-50.36-49.79Z",
  ],
  [
    "m310.99,225.18c0,30.75-21.52,51.5-50.35,51.5-16.14,0-29.98-6.92-38.43-19.99v56.31h-13.64v-138.36h13.07v19.99c8.26-13.45,22.29-20.76,39.01-20.76,28.82,0,50.34,20.76,50.34,51.31Zm-13.64,0c0-23.44-16.33-39.39-37.66-39.39s-37.66,15.95-37.66,39.39,16.14,39.39,37.66,39.39,37.66-15.75,37.66-39.39Z",
    "m228.15,318.94h-25.52v-150.24h24.95v10.31c8.93-7.16,20.38-11.08,33.07-11.08,32.61,0,56.28,24.08,56.28,57.25s-23.67,57.44-56.29,57.44c-12.55,0-23.68-3.7-32.49-10.64v46.96Zm-13.64-11.88h1.76v-70.5l1.7,2.63c-1.23-4.36-1.88-9.06-1.88-14.01,0-4.43.52-8.66,1.51-12.62l-1.9,3.09v-35.07h-1.19v126.48Zm35.68-37.5c3.3.78,6.8,1.17,10.45,1.17,26.15,0,44.41-18.73,44.41-45.56s-18.26-45.37-44.4-45.37c-.87,0-1.73.02-2.59.07.54-.02,1.08-.03,1.63-.03,25.26,0,43.6,19.06,43.6,45.33s-18.34,45.33-43.6,45.33c-3.29,0-6.47-.32-9.5-.95Zm9.5-77.83c-18.68,0-31.72,13.75-31.72,33.45s13.04,33.45,31.72,33.45,31.72-13.75,31.72-33.45-13.04-33.45-31.72-33.45Z",
  ],
  [
    "m413.03,251.32l7.69,8.84c-9.03,10.76-22.87,16.52-38.82,16.52-31.51,0-53.23-21.52-53.23-51.5s20.95-51.31,49.97-51.31c27.09,0,47.46,19.79,48.42,48.23l-83.01,16.14c5,16.34,19.22,26.33,38.05,26.33,12.48,0,23.44-4.41,30.93-13.25Zm-71.1-27.1c0,1.54,0,2.88.19,4.23l71.29-13.84c-2.88-16.53-16.14-29.02-34.78-29.02-21.52.01-36.7,15.76-36.7,38.63Z",
    "m381.9,282.62c-16.74,0-31.86-5.75-42.58-16.19-10.7-10.43-16.59-25.07-16.59-41.25,0-33.17,23.51-57.25,55.91-57.25,30.44,0,53.3,22.7,54.36,53.97l.17,5.06-80.83,15.72c5.58,10.1,16.29,15.95,29.76,15.95,11.09,0,20.22-3.86,26.4-11.15l4.47-5.28,15.56,17.89-3.26,3.89c-10.09,12.02-25.49,18.64-43.37,18.64Zm-16.99-100.9c-18.36,5.39-30.3,21.77-30.3,43.46,0,26.82,19.45,45.56,47.29,45.56,11.65,0,21.89-3.39,29.49-9.67-7.89,6.13-18.02,9.44-29.29,9.44-21.21,0-37.97-11.7-43.73-30.53l-1.93-6.31.41-.08-.61-4.31c-.25-1.76-.25-3.36-.25-5.06,0-12.57,4.23-23.93,11.92-31.99,4.66-4.88,10.47-8.45,17-10.51Zm13.72,9.81c-17.45,0-29.47,11.83-30.66,29.73l58.09-11.28c-4.18-11.38-14.43-18.46-27.42-18.46Zm17.76-8.17c11.89,5.37,20.43,16.21,22.87,30.23l.67,3.84.79-.15c-2.04-15.91-11.12-28.19-24.33-33.92Z",
  ],
  [
    "m547.93,217.11v79.82h-13.64v-78.47c0-21.33-11.15-32.28-30.36-32.28-21.72,0-35.36,13.45-35.36,36.51v53.04h-13.64v-101.09h13.07v18.64c7.3-12.3,20.95-19.41,38.43-19.41,24.59,0,41.5,14.22,41.5,43.24Z",
    "m553.87,302.49h-25.52v-84.03c0-17.72-7.99-26.34-24.42-26.34-18.7,0-29.42,11.14-29.42,30.57v58.98h-25.52v-112.97h24.95v9.23c8.58-6.47,19.8-10,32.49-10,29.71,0,47.44,18.39,47.44,49.18v85.38Zm-13.64-11.5h1.76v-73.88c0-24.05-12.63-37.3-35.56-37.3-3.51,0-6.84.31-9.96.93,2.38-.33,4.87-.5,7.46-.5,23.07,0,36.3,13.93,36.3,38.22v72.53Zm-79.36-21.2h1.76v-47.1c0-3.59.3-7,.88-10.2l-1.45,2.44v-34.35h-1.19v89.21Z",
  ],
  [
    "m674.02,328.42v134.51h-13.64v-107.61l-52.84,90.51h-6.73l-52.84-89.94v107.04h-13.64v-134.51h15.79l54.35,99.74,55.19-99.74h14.36Z",
    "m679.96,468.87h-25.52v-91.59l-43.49,74.49h-13.54l-43.5-74.04v91.14h-25.52v-146.39h25.25l50.87,93.34,51.65-93.34h23.8v146.39Zm-13.64-11.88h1.76v-122.63h-1.76v122.63Zm-126.05,0h1.76v-122.63h-1.76v122.63Zm1.94-122.63l60.44,102.88-56.06-102.88h-4.38Zm120.95,0l-46.79,84.56,49.37-84.56h-2.58Z",
  ],
  [
    "m704.96,446.6l5.57-10.95c9.61,9.42,26.71,16.33,44.39,16.33,25.17,0,36.12-10.57,36.12-23.83,0-36.9-82.82-14.22-82.82-63.99,0-19.79,15.37-36.9,49.58-36.9,15.18,0,30.94,4.42,41.7,11.92l-4.81,11.34c-11.53-7.5-24.98-11.14-36.9-11.14-24.6,0-35.55,10.95-35.55,24.41,0,36.9,82.82,14.6,82.82,63.6,0,19.79-15.76,36.7-50.15,36.7-20.17,0-39.96-7.12-49.95-17.49Z",
    "m754.91,470.03c-21.64,0-42.93-7.58-54.23-19.31l-2.93-3.04,11.16-21.94,5.78,5.67c9.07,8.89,24.86,14.63,40.23,14.63,19.18,0,30.18-6.52,30.18-17.89s-10.33-14.92-32.25-20.26c-22.53-5.49-50.57-12.32-50.57-43.73,0-12.07,5.01-22.88,14.1-30.44,9.76-8.11,24.08-12.4,41.42-12.4s33.43,4.85,45.1,12.99l3.95,2.76-9.46,22.3-5.94-3.86c-9.94-6.47-22.21-10.18-33.66-10.18-18.82,0-29.61,6.73-29.61,18.47s12.35,15.49,32.49,20.41c22.42,5.47,50.33,12.29,50.33,43.19,0,12.05-5.1,22.84-14.37,30.38-9.86,8.02-24.29,12.26-41.72,12.26Zm-42.61-24.77c9.73,7.81,26.2,12.88,42.61,12.88,27.27,0,44.21-11.79,44.21-30.76,0-20.07-16.34-25.56-41.27-31.65-19.48-4.75-41.55-10.14-41.55-31.95,0-14.67,10.9-30.35,41.49-30.35,11.42,0,23.5,3.07,34.06,8.56l.2-.46c-9.41-5.21-22.08-8.34-34.25-8.34-27.33,0-43.64,11.57-43.64,30.96,0,20.54,16.43,26.08,41.5,32.19,19.37,4.72,41.32,10.06,41.32,31.8,0,8.77-3.93,16.47-11.06,21.68-7.34,5.37-17.77,8.09-31,8.09-15.32,0-31.15-4.95-42.46-12.97l-.16.31Z",
  ],
];

const MESSAGES = [
  [0, "Starting {title}"],
  [5, "Loading OpenMS and its Python libraries"],
  [14, "Preparing your workspace"],
  [30, "The first start after an install takes a little longer"],
];

// Fonts of the app's theme, inlined so the page needs nothing from disk or
// the network; without them the system font is used.
function fontFace(fontDir, family, file, weight) {
  try {
    const data = fs.readFileSync(path.join(fontDir, file)).toString("base64");
    return `@font-face{font-family:"${family}";font-weight:${weight};src:url(data:font/woff2;base64,${data}) format("woff2")}`;
  } catch (_) {
    return "";
  }
}

// A fixed pseudo-random sequence, so the animation looks the same every time.
function seeded(i, k) {
  const v = Math.sin(i * 12.9898 + k * 78.233) * 43758.5453;
  return v - Math.floor(v);
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

function barRects(fill, cls) {
  return BARS.map(([x, y, w, h], i) => {
    const up = y < BASELINE;
    const low = (0.18 + 0.45 * seeded(i, 1)).toFixed(2);
    const high = (1 + 0.12 * seeded(i, 2)).toFixed(2);
    const dur = (0.9 + 1.3 * seeded(i, 3)).toFixed(2);
    const delay = (-2 * seeded(i, 4)).toFixed(2);
    const style = `--i:${i};--low:${low};--high:${high};--dur:${dur}s;--delay:${delay}s`;
    return `<rect class="bar ${up ? "up" : "down"} ${cls}" x="${x}" y="${y}" width="${w}" height="${h}" fill="${fill}" style="${style}"/>`;
  }).join("");
}

// The whole page as HTML. title and version come from the app's settings.json.
function loadingPage({ title, version, fontDir }) {
  const fonts = fontDir
    ? fontFace(fontDir, "Montserrat Alternates", "montserrat-alternates-latin-600-normal.woff2", 600) +
      fontFace(fontDir, "Raleway", "raleway-latin-500-normal.woff2", 500)
    : "";
  const glyphs = GLYPHS.map(
    (paths, i) => `<g class="glyph" style="--g:${i}">${paths.map((d) => `<path d="${d}"/>`).join("")}</g>`
  ).join("");
  const messages = MESSAGES.map(([at, text]) => [at, text.replace("{title}", title)]);
  return `<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(title)}</title><style>
${fonts}
:root{color-scheme:light dark;--bg:#eef1fd;--fg:#231f20;--muted:#5d5759;--track:#d3dbf7}
@media (prefers-color-scheme:dark){:root{--bg:#1a1718;--fg:#f9f8f9;--muted:#a8a0a2;--track:#3a3335}}
html,body{margin:0;background:var(--bg);color:var(--fg);overflow:hidden;
  font-family:Raleway,system-ui,-apple-system,"Segoe UI",sans-serif;-webkit-user-select:none;user-select:none;cursor:default}
html{height:100%}
body{position:relative;width:var(--window-width,100vw);height:var(--window-height,100vh);
  display:flex;align-items:center;justify-content:center}
html,body{transition:background-color .45s ease .2s}
html.done,body.done{background-color:transparent}
main{display:flex;flex-direction:column;align-items:center;width:min(640px,72vw);transition:opacity .45s ease,transform .45s ease}
svg{width:100%;height:auto;overflow:visible}
.glyph{fill:var(--fg);opacity:0;animation:glyph-in .7s cubic-bezier(.2,.8,.2,1) both;animation-delay:calc(.45s + var(--g) * 70ms)}
@keyframes glyph-in{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
.bar{transform-box:fill-box;transform:scaleY(0);
  animation:grow .75s cubic-bezier(.25,1.5,.45,1) calc(var(--i) * 45ms) forwards,
            live var(--dur) ease-in-out calc(1.6s + var(--delay) + 2s) infinite alternate}
.bar.down{transform-origin:50% 0}
.bar.up{transform-origin:50% 100%}
.sheen{mix-blend-mode:screen;pointer-events:none}
@keyframes grow{from{transform:scaleY(0)}to{transform:scaleY(1)}}
@keyframes live{0%{transform:scaleY(1)}50%{transform:scaleY(var(--low))}100%{transform:scaleY(var(--high))}}
.baseline{stroke:url(#openms-gradient);stroke-width:2.2;stroke-linecap:round;stroke-dasharray:780;stroke-dashoffset:780;
  animation:draw .6s ease-out forwards,fade-line .8s ease 1.2s forwards}
@keyframes draw{to{stroke-dashoffset:0}}
@keyframes fade-line{to{opacity:.35}}
h1{margin:26px 0 0;font:600 26px/1.2 "Montserrat Alternates",Raleway,system-ui,sans-serif;letter-spacing:.01em;
  opacity:0;animation:fade-in .6s ease 1s forwards}
.status{margin-top:10px;min-height:1.4em;font-size:15px;color:var(--muted);opacity:0;animation:fade-in .6s ease 1.3s forwards;
  transition:opacity .3s ease}
.status::after{content:"";display:inline-block;width:1.2em;text-align:left;animation:dots 1.4s steps(4) infinite}
@keyframes dots{0%{content:""}25%{content:"."}50%{content:".."}75%{content:"..."}}
.progress{margin-top:18px;width:180px;height:3px;border-radius:3px;background:var(--track);overflow:hidden;
  opacity:0;animation:fade-in .6s ease 1.3s forwards}
.progress::before{content:"";display:block;height:100%;width:40%;border-radius:3px;
  background:linear-gradient(90deg,#ffb401,#ff7501,#ff03cb,#b503ff,#3157e9);animation:slide 1.6s cubic-bezier(.6,0,.4,1) infinite}
@keyframes slide{from{transform:translateX(-100%)}to{transform:translateX(250%)}}
.version{position:absolute;bottom:18px;left:0;right:0;text-align:center;font-size:12px;color:var(--muted);
  opacity:0;animation:fade-in .6s ease 1.5s forwards}
@keyframes fade-in{to{opacity:1}}
body.done .bar{animation:none;transform:scaleY(1);transition:transform .35s cubic-bezier(.25,1.4,.45,1)}
body.done main{opacity:0;transform:scale(1.04);transition-delay:.2s}
body.done .version{opacity:0;transition:opacity .3s}
@media (prefers-reduced-motion:reduce){
  .bar,.glyph,.baseline,h1,.status,.progress,.version{animation:none!important;opacity:1;transform:none;stroke-dashoffset:0}
  .sheen,.progress::before{animation:none!important;display:none}
  body.done main{transform:none}
}
</style></head><body>
<main>
<svg viewBox="30 135 800 345" role="img" aria-label="OpenMS">
<defs>
<linearGradient id="openms-gradient" x1="44.08" y1="305.27" x2="811.73" y2="305.27" gradientUnits="userSpaceOnUse">
<stop offset="0" stop-color="#ffb401"/><stop offset=".05" stop-color="#ff9701"/><stop offset=".11" stop-color="#ff8401"/>
<stop offset=".22" stop-color="#ff7501"/><stop offset=".54" stop-color="#ff03cb"/><stop offset=".77" stop-color="#b503ff"/>
<stop offset=".91" stop-color="#3157e9"/></linearGradient>
<linearGradient id="openms-sheen" x1="-260" y1="0" x2="-60" y2="0" gradientUnits="userSpaceOnUse">
<stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".55"/>
<stop offset="1" stop-color="#fff" stop-opacity="0"/>
<animate attributeName="x1" values="-260;900" dur="2.4s" begin="1.4s" repeatCount="indefinite"/>
<animate attributeName="x2" values="-60;1100" dur="2.4s" begin="1.4s" repeatCount="indefinite"/>
</linearGradient>
</defs>
<line class="baseline" x1="44" y1="${BASELINE}" x2="812" y2="${BASELINE}"/>
<g>${barRects("url(#openms-gradient)", "")}</g>
<g class="sheen">${barRects("url(#openms-sheen)", "")}</g>
${glyphs}
</svg>
<h1>${escapeHtml(title)}</h1>
<div class="status" id="status"></div>
<div class="progress"></div>
</main>
<div class="version">${version ? "Version " + escapeHtml(version) + " &middot; " : ""}Powered by OpenMS</div>
<script>
const messages = ${JSON.stringify(messages).replace(/</g, "\\u003c")};
const status = document.getElementById("status");
const started = Date.now();
let shown = -1;
function update() {
  const t = (Date.now() - started) / 1000;
  let n = 0;
  messages.forEach(([at], i) => { if (t >= at) n = i; });
  if (n === shown) return;
  shown = n;
  status.style.opacity = 0;
  setTimeout(() => { status.textContent = messages[n][1]; status.style.opacity = ""; }, shown === 0 ? 0 : 300);
}
update();
setInterval(update, 500);
window.__finishLoading = () => new Promise((resolve) => {
  document.documentElement.classList.add("done");
  document.body.classList.add("done");
  setTimeout(resolve, 700);
});
</script>
</body></html>`;
}

function loadingPageUrl(options) {
  return "data:text/html;charset=utf-8," + encodeURIComponent(loadingPage(options));
}

// Run in the loading screen once the app page is ready behind it; resolves
// once the bars are back in the logo and the screen has faded out.
const FINISH_SCRIPT = "window.__finishLoading ? window.__finishLoading() : null";

// Run in the app page: true once Streamlit has finished running the page
// script and the main area holds at least one element.
const APP_READY_SCRIPT = `(() => {
  const root = document.querySelector('[data-testid="stApp"]');
  if (!root || root.getAttribute("data-test-script-state") !== "notRunning") return false;
  return !!document.querySelector('[data-testid="stMain"] [data-testid="stElementContainer"]');
})()`;

// Where the loading view goes: at the window's top left corner, and at least
// as large as the window and every display, so no edge of the app page shows
// while the window grows faster than its size is reported. The window clips
// the rest. Sizes are [width, height].
function overlayBounds(windowSize, displaySizes = []) {
  const [width, height] = windowSize;
  return {
    x: 0,
    y: 0,
    width: Math.max(width, ...displaySizes.map((d) => d.width)),
    height: Math.max(height, ...displaySizes.map((d) => d.height)),
  };
}

// Run in the loading screen: centres the logo in the part of the view the
// window shows.
function windowSizeScript([width, height]) {
  const w = Math.max(0, Math.round(width));
  const h = Math.max(0, Math.round(height));
  return `(() => { const s = document.documentElement.style;
    s.setProperty("--window-width", "${w}px"); s.setProperty("--window-height", "${h}px"); })()`;
}

// The window's own background, so no white frame flashes between the pages.
function backgroundColor(dark) {
  return dark ? "#1a1718" : "#eef1fd";
}

module.exports = {
  loadingPage,
  loadingPageUrl,
  overlayBounds,
  windowSizeScript,
  FINISH_SCRIPT,
  APP_READY_SCRIPT,
  backgroundColor,
  BARS,
  GLYPHS,
};
