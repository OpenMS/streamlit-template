// Feature linking across files, stored as consensusXML like the TOPP tool.
//
// The WebAssembly build has no feature grouping algorithm, so this is a
// TypeScript stand-in for FeatureLinkerUnlabeledKD's linking step: from the
// most intense feature down, each unlinked feature takes from every other file
// the closest unlinked feature within the RT and m/z tolerances (with a
// compatible charge). It does no RT alignment (the TOPP tool's "warp").

import type { FeatureData } from "../../../public/openms/openms";
import type { ParamDef } from "../workflow/params";
import { stageIn, unlink, type ToolDef } from "./types";

const LINK = "algorithm:link";
const section = { section: LINK, sectionDescription: "Feature linking", advanced: false };

const PARAMS: ParamDef[] = [
  { key: `${LINK}:rt_tol`, type: "double", default: 100, min: 0, description: "Width of RT tolerance window (sec)", ...section },
  { key: `${LINK}:mz_tol`, type: "double", default: 10, min: 0, description: "m/z tolerance (in ppm or Da)", ...section },
  { key: `${LINK}:mz_unit`, type: "string", default: "ppm", validStrings: ["ppm", "Da"], description: "Unit of m/z tolerance", ...section },
  {
    key: `${LINK}:charge_merging`,
    type: "string",
    default: "With_charge_zero",
    validStrings: ["Identical", "With_charge_zero", "Any"],
    description:
      "whether to disallow charge mismatches (Identical), allow to link charge zero (i.e., unknown charge state) with every charge state, or disregard charges (Any).",
    ...section,
  },
];

type F = { map: number; id: string; rt: number; mz: number; intensity: number; charge: number; linked: boolean };
export type Group = { elements: F[]; quality: number };

export type LinkOptions = { rtTol: number; mzTol: number; ppm: boolean; chargeMerging: string };

const chargesFit = (a: number, b: number, mode: string) =>
  mode === "Any" || a === b || (mode === "With_charge_zero" && (a === 0 || b === 0));

/** Links features of several maps; every feature ends up in exactly one group */
export function link(maps: FeatureData[][], o: LinkOptions): Group[] {
  const byMap: F[][] = maps.map((fs, map) =>
    fs.map((f) => ({ map, id: f.uniqueId, rt: f.rt, mz: f.mz, intensity: f.intensity, charge: f.charge, linked: false })).sort((a, b) => a.mz - b.mz),
  );
  const all = byMap.flat().sort((a, b) => b.intensity - a.intensity);
  const mzTol = (mz: number) => (o.ppm ? (mz * o.mzTol) / 1e6 : o.mzTol);
  const groups: Group[] = [];
  for (const seed of all) {
    if (seed.linked) continue;
    seed.linked = true;
    const elements = [seed];
    const distances: number[] = [];
    const tol = mzTol(seed.mz);
    for (const [m, fs] of byMap.entries()) {
      if (m === seed.map) continue;
      let best: F | null = null;
      let bestD = Infinity;
      // first feature with mz >= seed.mz - tol
      let lo = 0;
      let hi = fs.length;
      while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (fs[mid].mz < seed.mz - tol) lo = mid + 1;
        else hi = mid;
      }
      for (let i = lo; i < fs.length && fs[i].mz <= seed.mz + tol; i++) {
        const f = fs[i];
        if (f.linked || Math.abs(f.rt - seed.rt) > o.rtTol || !chargesFit(f.charge, seed.charge, o.chargeMerging)) continue;
        const d = Math.hypot((f.rt - seed.rt) / (o.rtTol || 1), (f.mz - seed.mz) / (tol || 1)) / Math.SQRT2;
        if (d < bestD) [best, bestD] = [f, d];
      }
      if (best) {
        best.linked = true;
        elements.push(best);
        distances.push(bestD);
      }
    }
    // the share of files linked, lowered by how far apart the features are
    const spread = distances.length ? distances.reduce((a, b) => a + b, 0) / distances.length : 0;
    const quality = maps.length > 1 ? ((elements.length - 1) / (maps.length - 1)) * (1 - spread) : 1;
    groups.push({ elements: elements.sort((a, b) => a.map - b.map), quality });
  }
  return groups;
}

const xmlAttr = (s: string) => s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
const uid = () => BigInt.asUintN(64, BigInt(Math.floor(Math.random() * 2 ** 53)) * 2048n + BigInt(Math.floor(Math.random() * 2048))).toString();

/** The consensusXML of the groups (schema 1.7), as ConsensusXMLFile writes it */
export function consensusXML(files: { name: string; size: number; id: string }[], groups: Group[]): string {
  const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;
  const out = [
    '<?xml version="1.0" encoding="ISO-8859-1"?>',
    `<consensusXML version="1.7" id="cm_${uid()}" experiment_type="label-free" xsi:noNamespaceSchemaLocation="https://raw.githubusercontent.com/OpenMS/OpenMS/develop/share/OpenMS/SCHEMAS/ConsensusXML_1_7.xsd" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">`,
    `\t<mapList count="${files.length}">`,
    ...files.map((f, i) => `\t\t<map id="${i}" name="${xmlAttr(f.name)}" unique_id="${f.id}" label="" size="${f.size}">\n\t\t</map>`),
    "\t</mapList>",
    "\t<consensusElementList>",
  ];
  for (const g of groups) {
    const e = g.elements;
    const charge = e.find((f) => f.charge)?.charge ?? 0;
    out.push(
      `\t\t<consensusElement id="e_${uid()}" quality="${g.quality}" charge="${charge}">`,
      `\t\t\t<centroid rt="${mean(e.map((f) => f.rt))}" mz="${mean(e.map((f) => f.mz))}" it="${mean(e.map((f) => f.intensity))}"/>`,
      "\t\t\t<groupedElementList>",
      ...e.map((f) => `\t\t\t\t<element map="${f.map}" id="${f.id}" rt="${f.rt}" mz="${f.mz}" it="${f.intensity}" charge="${f.charge}"/>`),
      "\t\t\t</groupedElementList>",
      "\t\t</consensusElement>",
    );
  }
  out.push("\t</consensusElementList>", "</consensusXML>", "");
  return out.join("\n");
}

export const FeatureLinkerUnlabeledKD: ToolDef = {
  name: "FeatureLinkerUnlabeledKD",
  description: "Groups corresponding features from multiple maps (a TypeScript stand-in for the linking of the TOPP tool, without RT alignment).",
  io: { in: { many: true }, out: { output: true } },
  params: () => PARAMS,
  async run(env, io, v) {
    const { O } = env;
    if (io.in.length < 2) env.log("Only one feature map: every feature becomes its own consensus feature.", 2);
    const maps: FeatureData[][] = [];
    const files = [];
    for (const path of io.in) {
      const local = await stageIn(env, path);
      const fm = new O.FeatureMap();
      const xml = new O.FeatureXMLFile();
      try {
        xml.load(local, fm);
        maps.push(fm.toArray());
        files.push({ name: path, size: fm.size(), id: uid() });
      } finally {
        xml.delete();
        fm.delete();
        unlink(env, local);
      }
    }
    const groups = link(maps, {
      rtTol: Number(v[`${LINK}:rt_tol`]),
      mzTol: Number(v[`${LINK}:mz_tol`]),
      ppm: v[`${LINK}:mz_unit`] === "ppm",
      chargeMerging: String(v[`${LINK}:charge_merging`]),
    });
    env.log(`Linked ${maps.reduce((n, m) => n + m.length, 0)} features of ${maps.length} maps into ${groups.length} consensus features.`, 2);
    await env.store.write(io.out[0], consensusXML(files, groups));
  },
};
