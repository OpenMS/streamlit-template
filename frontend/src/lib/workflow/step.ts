// A step: the counterpart of a Python tool of src/python-tools. DEFAULTS
// declares its parameters with the same keys, so the configure page generates
// their widgets (ui.input_python); run() gets the parameter values merged with
// the files passed to ctx.runStep, as the script gets its JSON file.

import type { OpenMS } from "../engine/openms";
import type { Store } from "../storage/store";

export type StepDefault = {
  key: string;
  value: unknown;
  name?: string;
  help?: string;
  hide?: boolean;
  options?: unknown[];
  min?: number;
  max?: number;
  step_size?: number;
  widget_type?: "auto" | "text" | "textarea" | "number" | "selectbox" | "slider" | "checkbox" | "multiselect" | "password";
  advanced?: boolean;
};

export type StepEnv = {
  O: OpenMS;
  store: Store;
  /** As the script's stdout: the "all" log */
  log: (message: string) => void;
};

export type StepDef = {
  name: string;
  DEFAULTS: StepDefault[];
  run: (env: StepEnv, params: Record<string, any>) => Promise<void>;
};

/** "<step>.ts:<key>", the key of a step parameter in params.json */
export const stepKey = (step: string, key: string) => `${step}.ts:${key}`;
