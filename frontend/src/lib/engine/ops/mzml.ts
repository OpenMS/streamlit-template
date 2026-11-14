// The "pyOpenMS Workflow" pages on the WebAssembly module: the raw data viewer
// (src/view.py), the example workflow (src/mzmlfileworkflow.py) and the ID
// extraction of content/run_subprocess.py.

import type { MSExperiment } from "../../../../public/openms/openms";
import type { Store } from "../../storage/store";
import type { OpenMS } from "../openms";

const cache = new Map<string, MSExperiment>();

/** Copies a stored file into the module's file system and returns its path there */
export async function stage(O: OpenMS, store: Store, path: string): Promise<string> {
  const bytes = await store.read(path);
  if (!bytes) throw new Error(`File not found: ${path}`);
  const dest = `/work/${path}`;
  O.FS.mkdirTree(dest.slice(0, dest.lastIndexOf("/")), 0o777);
  O.FS.writeFile(dest, bytes);
  return dest;
}

export async function loadExperiment(O: OpenMS, store: Store, path: string): Promise<MSExperiment> {
  const f = await store.file(path);
  if (!f) throw new Error(`File not found: ${path}`);
  const key = `${path}|${f.lastModified}|${f.size}`;
  const hit = cache.get(key);
  if (hit) return hit;
  const local = await stage(O, store, path);
  const exp = new O.MSExperiment();
  const file = new O.MzMLFile();
  try {
    file.load(local, exp);
  } finally {
    file.delete();
    O.FS.unlink(local);
  }
  exp.sortSpectra(true);
  // keep the two most recent files
  while (cache.size >= 2) {
    const [k, e] = cache.entries().next().value!;
    e.delete();
    cache.delete(k);
  }
  cache.set(key, exp);
  return exp;
}

export async function overview(O: OpenMS, store: Store, path: string) {
  const exp = await loadExperiment(O, store, path);
  const spectra = [];
  const chromatograms: Record<string, { rt: number[]; tic: number[]; bpc: number[] }> = {};
  for (const s of exp.getSpectrumSummary()) {
    if (!s.size) continue;
    spectra.push({
      index: s.index,
      RT: round(s.rt, 4),
      "MS level": s.msLevel,
      "precursor m/z": s.precursorMZ != null ? round(s.precursorMZ, 4) : null,
      "max intensity m/z": s.basePeakMZ != null ? round(s.basePeakMZ, 4) : null,
      peaks: s.size,
      TIC: s.tic,
    });
    const c = (chromatograms[s.msLevel] ??= { rt: [], tic: [], bpc: [] });
    c.rt.push(s.rt);
    c.tic.push(s.tic);
    c.bpc.push(s.basePeakIntensity ?? 0);
  }
  return { spectra, chromatograms };
}

export async function spectrum(O: OpenMS, store: Store, path: string, index: number) {
  const exp = await loadExperiment(O, store, path);
  if (index < 0 || index >= exp.getNrSpectra()) throw new Error("No such spectrum");
  const s = exp.getSpectrum(index);
  try {
    const { mz, intensity } = s.getPeaks();
    return {
      index,
      rt: s.getRT(),
      ms_level: s.getMSLevel(),
      precursor_mz: s.getPrecursors()[0]?.mz ?? null,
      mz: Array.from(mz),
      intensity: Array.from(intensity),
    };
  } finally {
    s.delete();
  }
}

export type PeakMapRequest = {
  path: string;
  ms_level?: number;
  rt_min?: number | null;
  rt_max?: number | null;
  mz_min?: number | null;
  mz_max?: number | null;
  intensity_cutoff?: number;
  rt_bins?: number;
  mz_bins?: number;
};

/** The peak map binned to at most rt_bins x mz_bins points (the most intense peak per bin) */
export async function peakMap(O: OpenMS, store: Store, r: PeakMapRequest) {
  const exp = await loadExperiment(O, store, r.path);
  const level = r.ms_level ?? 1;
  const rts: number[] = [];
  const mzs: number[] = [];
  const ints: number[] = [];
  for (const s of exp.getSpectrumSummary()) {
    if (s.msLevel !== level || !s.size) continue;
    if ((r.rt_min != null && s.rt < r.rt_min) || (r.rt_max != null && s.rt > r.rt_max)) continue;
    const spec = exp.getSpectrum(s.index);
    const { mz, intensity } = spec.getPeaks();
    spec.delete();
    for (let i = 0; i < mz.length; i++) {
      if (intensity[i] < (r.intensity_cutoff ?? 0)) continue;
      if ((r.mz_min != null && mz[i] < r.mz_min) || (r.mz_max != null && mz[i] > r.mz_max)) continue;
      rts.push(s.rt);
      mzs.push(mz[i]);
      ints.push(intensity[i]);
    }
  }
  const total = rts.length;
  if (!total) return { rt: [], mz: [], intensity: [], total_peaks: 0 };
  const rb = r.rt_bins ?? 400;
  const mb = r.mz_bins ?? 400;
  const [rtLo, rtHi] = extent(rts);
  const [mzLo, mzHi] = extent(mzs);
  const best = new Map<number, number>();
  for (let i = 0; i < total; i++) {
    const ri = Math.min(rb - 1, Math.floor(((rts[i] - rtLo) / (rtHi - rtLo + 1e-9)) * rb));
    const mi = Math.min(mb - 1, Math.floor(((mzs[i] - mzLo) / (mzHi - mzLo + 1e-9)) * mb));
    const bin = ri * mb + mi;
    const j = best.get(bin);
    if (j === undefined || ints[i] > ints[j]) best.set(bin, i);
  }
  const keep = [...best.values()].sort((a, b) => ints[a] - ints[b]);
  return {
    rt: keep.map((i) => round(rts[i], 4)),
    mz: keep.map((i) => round(mzs[i], 5)),
    intensity: keep.map((i) => ints[i]),
    total_peaks: total,
  };
}

export async function countSpectra(O: OpenMS, store: Store, path: string) {
  return (await loadExperiment(O, store, path)).size();
}

/** The idRef lines of an mzML file, as `grep idRef` prints them in content/run_subprocess.py */
export async function extractIds(store: Store, path: string) {
  const text = await store.readText(path);
  if (text === null) throw new Error(`File not found: ${path}`);
  const lines = text.split("\n").filter((l) => l.includes("idRef"));
  return lines.join("\n");
}

function extent(xs: number[]): [number, number] {
  let lo = Infinity;
  let hi = -Infinity;
  for (const x of xs) {
    if (x < lo) lo = x;
    if (x > hi) hi = x;
  }
  return [lo, hi];
}

const round = (x: number, d: number) => Math.round(x * 10 ** d) / 10 ** d;
