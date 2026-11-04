// The example workflow, as src/Workflow.py: detect metabolite features in each
// mzML file, link them across files and export them as a table.

import { Markdown, SelectFiles, Step, Tab, Tool, Upload, Widget, type WorkflowSpec } from "../lib/workflow/spec";

export const toppWorkflow: WorkflowSpec = {
  name: "TOPP Workflow",
  description: "Detect metabolite features in each mzML file and link them across files.",
  upload: [
    Upload("mzML-files", ["mzML"], {
      name: "MS data",
      fallback: ["example-data/mzML/Blank.mzML", "example-data/mzML/Control.mzML", "example-data/mzML/Pool.mzML", "example-data/mzML/Treatment.mzML"],
    }),
  ],
  configure: [
    SelectFiles("mzML-files", { name: "mzML files", multiple: true }),
    Tab("Feature Detection", [Tool("FeatureFinderMetabo", { customDefaults: { "algorithm:common:noise_threshold_int": 1000.0 } })]),
    Tab("Feature Linking", [Tool("FeatureLinkerUnlabeledKD")]),
    Tab("Custom Step", [
      Widget("run-python-script", false, "Run custom step", { widgetType: "checkbox" }),
      Markdown("The step of `src/steps/example.ts`, with widgets generated from its `DEFAULTS`.", { visibleIf: { key: "run-python-script", equals: true } }),
      Step("example", { visibleIf: { key: "run-python-script", equals: true } }),
    ]),
  ],
  results: [{ component: "consensus-features", title: "Consensus features", props: { file: "results/feature-linking/feature_matrix.tsv" } }],

  async execute(ctx) {
    // Any parameter checks, here simply checking if mzML files are selected
    if (!ctx.params["mzML-files"]?.length) {
      ctx.log("ERROR: No mzML files selected.");
      return false;
    }
    const inMzML = ctx.getFiles(ctx.params["mzML-files"]);
    ctx.log(`Number of input mzML files: ${inMzML.length}`);

    // Feature detection, one command per file
    const outFFM = ctx.getFiles(inMzML, "featureXML", "feature-detection");
    ctx.log("Detecting features...");
    if (!(await ctx.runTool("FeatureFinderMetabo", { in: inMzML, out: outFFM }))) {
      ctx.log("ERROR: Feature detection failed.");
      return false;
    }

    // Feature linking, all feature maps in one command
    const inFL = ctx.getFiles(outFFM, undefined, undefined, true);
    const outFL = ctx.getFiles("feature_matrix.consensusXML", undefined, "feature-linking");
    ctx.log("Linking features...");
    if (!(await ctx.runTool("FeatureLinkerUnlabeledKD", { in: inFL, out: outFL }))) {
      ctx.log("ERROR: Feature linking failed.");
      return false;
    }

    ctx.log("Exporting consensus features to a table...");
    if (!(await ctx.runStep("export_consensus_feature_df", { in: outFL[0] }))) {
      ctx.log("ERROR: Exporting consensus features failed.");
      return false;
    }

    if (ctx.params["run-python-script"]) {
      if (!(await ctx.runStep("example", { in: inMzML }))) {
        ctx.log("ERROR: Custom step failed.");
        return false;
      }
    }
    return true;
  },
};
