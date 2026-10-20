// The example step (src/python-tools/example.py): it logs its parameters.

import type { StepDef } from "../lib/workflow/step";

export const example: StepDef = {
  name: "example",
  DEFAULTS: [
    { key: "in", value: [], help: "Input files for the step.", hide: true },
    { key: "out", value: [], help: "Output files for the step.", hide: true },
    {
      key: "number-slider",
      name: "number of features",
      value: 6,
      min: 2,
      max: 10,
      help: "How many features to consider.",
      widget_type: "slider",
      step_size: 2,
    },
    { key: "selectbox-example", name: "select something", value: "a", options: ["a", "b", "c"] },
    { key: "adavanced-input", name: "advanced parameter", value: 5, step_size: 5, help: "An advanced example parameter.", advanced: true },
    { key: "checkbox", value: true, name: "boolean" },
  ],
  async run({ log }, params) {
    // Add code here:
    log("Writing output which will get logged...");
    log("Parameters for this example step:");
    log(JSON.stringify(params, null, 4));
  },
};
