// FeatureFinderMetabo on the WebAssembly module, with the TOPP tool's
// parameters (algorithm:common, :mtd, :epd, :ffm) and steps: mass trace
// detection on the MS1 spectra, elution peak detection, feature finding.

import type { ParamDef } from "../workflow/params";
import { algorithmParams, localPath, sectionValues, stageIn, stageOut, unlink, type ToolDef } from "./types";

// Shared by the sub-algorithms, as the TOPP tool's "algorithm:common" section
const COMMON = ["noise_threshold_int", "chrom_peak_snr", "chrom_fwhm"];

function params(O: Parameters<ToolDef["params"]>[0]): ParamDef[] {
  const mtd = algorithmParams(O, "MassTraceDetection", "algorithm:mtd", { sectionDescription: "Mass trace detection" });
  const epd = algorithmParams(O, "ElutionPeakDetection", "algorithm:epd", { sectionDescription: "Elution peak detection" });
  const ffm = algorithmParams(O, "FeatureFindingMetabo", "algorithm:ffm", { sectionDescription: "Feature finding" });
  const all = [...mtd, ...epd, ...ffm];
  const common: ParamDef[] = COMMON.map((name) => {
    const d = all.find((p) => p.key.endsWith(`:${name}`))!;
    return { ...d, key: `algorithm:common:${name}`, section: "algorithm:common", sectionDescription: "Parameters shared by the steps", advanced: false };
  });
  const enabled: ParamDef = {
    key: "algorithm:epd:enabled",
    type: "bool",
    default: "true",
    description: "Enables or disables the chromatographic peak detection of mass traces",
    advanced: false,
    section: "algorithm:epd",
    sectionDescription: "Elution peak detection",
  };
  const own = (d: ParamDef) => !COMMON.includes(d.key.split(":").at(-1)!);
  return [...common, ...mtd.filter(own), enabled, ...epd.filter(own), ...ffm.filter(own)];
}

/** A sub-algorithm's values: its section plus the common values it takes */
function values(defs: ParamDef[], v: Record<string, unknown>, section: string, takes: string[]) {
  const out = sectionValues(defs, v, section, ["enabled"]);
  for (const name of takes) out[name] = Number(v[`algorithm:common:${name}`]);
  return out;
}

export const FeatureFinderMetabo: ToolDef = {
  name: "FeatureFinderMetabo",
  description: "Assembles metabolite features from centroided (LC-)MS data using the mass trace approach.",
  io: { in: {}, out: { output: true } },
  params,
  async run(env, io, v) {
    const { O } = env;
    const defs = params(O);
    const input = await stageIn(env, io.in[0]);
    const out = localPath(env, io.out[0]);
    const exp = new O.MSExperiment();
    const traces = new O.MassTraceList();
    const split = new O.MassTraceList();
    const features = new O.FeatureMap();
    const file = new O.MzMLFile();
    const mtd = new O.MassTraceDetection();
    const epd = new O.ElutionPeakDetection();
    const ffm = new O.FeatureFindingMetabo();
    const xml = new O.FeatureXMLFile();
    try {
      file.setOptions({ msLevels: [1] });
      file.load(input, exp);
      unlink(env, input);
      if (!exp.size()) throw new Error("The input file contains no MS1 spectra.");
      env.log(`Loaded ${exp.size()} MS1 spectra.`, 2);

      mtd.setParameterValues(values(defs, v, "algorithm:mtd", ["noise_threshold_int", "chrom_peak_snr"]));
      mtd.run(exp, traces);
      env.log(`Mass traces detected: ${traces.size()}`, 2);

      let found = traces;
      if (v["algorithm:epd:enabled"] === "true") {
        epd.setParameterValues(values(defs, v, "algorithm:epd", ["chrom_fwhm", "chrom_peak_snr"]));
        epd.detectPeaks(traces, split);
        env.log(`Mass traces after elution peak detection: ${split.size()}`, 2);
        found = split;
      }

      ffm.setParameterValues(values(defs, v, "algorithm:ffm", ["chrom_fwhm"]));
      ffm.run(found, features);
      features.ensureUniqueIds();
      env.log(`Features found: ${features.size()}`, 2);

      xml.store(out, features);
    } finally {
      for (const h of [xml, ffm, epd, mtd, file, features, split, traces, exp]) h.delete();
    }
    await stageOut(env, out, io.out[0]);
  },
};
