import { describe, expect, it } from "vitest";
import * as toolbox from "../src/lib/engine/ops/toolbox";
import { runWorkflow } from "../src/lib/workflow/runner";
import { toppWorkflow } from "../src/workflows/topp-workflow";
import { openms, storeWithExamples } from "./openms";

describe("the example workflow on the OpenMS WebAssembly module", () => {
  it("detects, links and exports features of the example files", async () => {
    const O = await openms();
    const wd = "default/topp-workflow";
    const { store, paths } = await storeWithExamples(`${wd}/input-files/mzML-files`);
    await store.write(`${wd}/params.json`, JSON.stringify({ "mzML-files": paths, "run-python-script": true, _defaults: { FeatureFinderMetabo: { "algorithm:common:noise_threshold_int": 1000 } } }));

    expect(await runWorkflow(O, store, toppWorkflow, wd, 0)).toBe("finished");

    for (const name of ["Blank", "Control", "Pool", "Treatment"]) expect(await store.exists(`${wd}/results/feature-detection/${name}.featureXML`)).toBe(true);
    const tsv = (await store.readText(`${wd}/results/feature-linking/feature_matrix.tsv`))!.trim().split("\n");
    expect(tsv[0].split("\t")).toEqual(["metabolite", "charge", "rt", "mz", "quality", "Blank.featureXML", "Control.featureXML", "Pool.featureXML", "Treatment.featureXML"]);
    expect(tsv.length).toBeGreaterThan(1000);
    const log = (await store.readText(`${wd}/logs/all.log`))!;
    expect(log).toContain("Parameters for this example step");
    expect(log).toContain("-algorithm:common:noise_threshold_int 1000");
  });

  it("reports a failed step as an error, without the finished marker", async () => {
    const O = await openms();
    const { store } = await storeWithExamples("w/topp-workflow/input-files/mzML-files");
    await store.write("w/topp-workflow/params.json", JSON.stringify({ "mzML-files": ["w/missing.mzML"] }));
    expect(await runWorkflow(O, store, toppWorkflow, "w/topp-workflow", 0)).toBe("error");
    expect(await store.readText("w/topp-workflow/logs/minimal.log")).toContain("ERROR: Feature detection failed.");
  });
});

describe("toolbox ports", () => {
  it("match pyOpenMS values", async () => {
    const O = await openms();
    expect(toolbox.peptideMz(O, "PEPTIDE", 1, 2).charge_results[1].mz_ratio).toBeCloseTo(800.36725, 4);
    const iso = toolbox.isotopePattern(O, { method: "formula", value: "C6H12O6" });
    expect(iso.mzs[0]).toBeCloseTo(180.0634, 4);
    expect(toolbox.fragments(O, "PEPTIDE").fragments.rows).toHaveLength(12);
    expect(toolbox.digest(O, { fasta: ">sp|P1|X\nMKPEPTIDERAAAAAAK" }).table.rows.length).toBeGreaterThan(0);
  });
});
