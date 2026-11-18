import { describe, expect, it } from "vitest";
import { applyPreset, coerce, effectiveValues, matches, registerCustomDefaults, setToolValues, summary, type ParamDef } from "../src/lib/workflow/params";

const defs: ParamDef[] = [
  { key: "algorithm:common:noise_threshold_int", type: "double", default: 10, description: "", advanced: false, section: "algorithm:common" },
  { key: "algorithm:epd:enabled", type: "bool", default: "true", description: "", advanced: false, section: "algorithm:epd" },
  { key: "algorithm:ffm:charge_upper_bound", type: "int", default: 3, description: "", advanced: false, section: "algorithm:ffm" },
];

describe("parameters, stored as the Streamlit ParameterManager stores them", () => {
  it("coerces values to their type, bools as TOPP strings", () => {
    expect(coerce("bool", true)).toBe("true");
    expect(coerce("bool", "False")).toBe("false");
    expect(coerce("int", "4.7")).toBe(4);
    expect(coerce("double-list", "1\n2.5\n")).toEqual([1, 2.5]);
  });

  it("stores only values that differ from the effective default", () => {
    const stored: Record<string, any> = {};
    registerCustomDefaults(stored, "FeatureFinderMetabo", { "algorithm:common:noise_threshold_int": 1000 });
    setToolValues(defs, stored, "FeatureFinderMetabo", { "algorithm:common:noise_threshold_int": 1000, "algorithm:ffm:charge_upper_bound": 5 });
    expect(stored.FeatureFinderMetabo).toEqual({ "algorithm:ffm:charge_upper_bound": 5 });
    expect(effectiveValues(defs, stored, "FeatureFinderMetabo")).toEqual({
      "algorithm:common:noise_threshold_int": 1000,
      "algorithm:epd:enabled": "true",
      "algorithm:ffm:charge_upper_bound": 5,
    });
    setToolValues(defs, stored, "FeatureFinderMetabo", { "algorithm:ffm:charge_upper_bound": 3 });
    expect(stored.FeatureFinderMetabo).toBeUndefined();
  });

  it("applies presets.json presets and summarises non-defaults", () => {
    const stored: Record<string, any> = { "mzML-files": ["ws/wf/input-files/mzML-files/a.mzML"], "example.ts:checkbox": false };
    applyPreset(stored, { _description: "x", FeatureFinderMetabo: { "algorithm:common:noise_threshold_int": 500 }, _general: { "run-python-script": true } });
    const s = summary(stored);
    expect(s.tools.FeatureFinderMetabo).toEqual({ "algorithm:common:noise_threshold_int": 500 });
    expect(s.general).toEqual({ "mzML-files": ["a.mzML"], "run-python-script": true });
    expect(s.steps).toEqual({ "example.ts": { checkbox: false } });
  });

  it("matches excluded parameters by suffix, as input_TOPP does", () => {
    expect(matches("noise_threshold_int", "algorithm:common:noise_threshold_int")).toBe(true);
    expect(matches(":common:noise_threshold_int", "algorithm:common:noise_threshold_int")).toBe(true);
    expect(matches("threshold_int", "algorithm:common:noise_threshold_int")).toBe(false);
  });
});
