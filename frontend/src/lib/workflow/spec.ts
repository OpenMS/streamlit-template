// Declaring a workflow: the TypeScript counterpart of a WorkflowManager
// subclass. upload, configure and results describe the pages, as the
// StreamlitUI calls in upload()/configure()/results() do; execute() runs in a
// Web Worker on the OpenMS WebAssembly module, as execution() does.
//
//   Streamlit (src/Workflow.py)         here (src/workflows/*.ts)
//   ui.upload_widget(key, ...)          Upload(key, ...)
//   ui.select_input_file(key, ...)      SelectFiles(key, ...)
//   ui.input_widget(key, value, ...)    Widget(key, value, ...)
//   ui.input_TOPP(tool, ...)            Tool(tool, ...)
//   ui.input_python(script)             Step(name)
//   st.tabs([...])                      Tab(title, [...])
//   reactive=True + if                  visibleIf: { key, equals }
//   executor.run_topp / run_python      ctx.runTool / ctx.runStep

import type { RunContext } from "./context";

export type VisibleIf = { key: string; equals: unknown };

export type Upload = {
  kind: "upload";
  key: string;
  name: string;
  fileTypes: string[];
  /** URLs of example files offered until the user adds files of their own */
  fallback?: string[];
};

export type SelectFiles = { kind: "select-files"; key: string; name: string; multiple: boolean; visibleIf?: VisibleIf };

export type WidgetType = "auto" | "text" | "textarea" | "number" | "selectbox" | "slider" | "checkbox" | "multiselect" | "password";

export type Widget = {
  kind: "widget";
  key: string;
  default: unknown;
  name: string;
  help?: string;
  widgetType?: WidgetType;
  options?: unknown[];
  min?: number;
  max?: number;
  step?: number;
  advanced?: boolean;
  visibleIf?: VisibleIf;
};

export type Tool = {
  kind: "tool";
  tool: string;
  /** Parameters are stored under this name, so one tool can appear twice (tool_instance_name) */
  instance?: string;
  excludeParameters?: string[];
  includeParameters?: string[];
  customDefaults?: Record<string, unknown>;
  displayToolName?: boolean;
  displaySubsections?: boolean;
  visibleIf?: VisibleIf;
};

export type Step = { kind: "step"; step: string; visibleIf?: VisibleIf };
export type Markdown = { kind: "markdown"; text: string; visibleIf?: VisibleIf };
export type Tab = { kind: "tab"; title: string; items: ConfigItem[] };
export type ConfigItem = SelectFiles | Widget | Tool | Step | Markdown | Tab;

/** A block of the results page: a component of src/lib/results/registry.ts and its props */
export type ResultView = { component: string; title?: string; props?: Record<string, unknown> };

export type WorkflowSpec = {
  name: string;
  description?: string;
  upload: Upload[];
  configure: ConfigItem[];
  results: ResultView[];
  /** Runs the workflow; true only if every step succeeded (as execution() -> bool) */
  execute: (ctx: RunContext) => Promise<boolean>;
};

/** "TOPP Workflow" -> "topp-workflow", as the Streamlit workflow directory */
export const slugOf = (name: string) => name.toLowerCase().replace(/ /g, "-");

export const toolInstance = (t: Tool) => t.instance ?? t.tool;

export function* walkItems(items: ConfigItem[]): Generator<ConfigItem> {
  for (const it of items) {
    if (it.kind === "tab") yield* walkItems(it.items);
    else yield it;
  }
}

// Constructors, so a workflow reads like its Streamlit configure()

export const Upload = (key: string, fileTypes: string[], o: Partial<Omit<Upload, "kind" | "key" | "fileTypes">> = {}): Upload => ({
  kind: "upload",
  key,
  fileTypes,
  name: o.name ?? key,
  ...o,
});
export const SelectFiles = (key: string, o: Partial<Omit<SelectFiles, "kind" | "key">> = {}): SelectFiles => ({
  kind: "select-files",
  key,
  name: o.name ?? key,
  multiple: o.multiple ?? true,
  ...o,
});
export const Widget = (key: string, value: unknown, name: string, o: Partial<Omit<Widget, "kind" | "key" | "default" | "name">> = {}): Widget => ({
  kind: "widget",
  key,
  default: value,
  name,
  ...o,
});
export const Tool = (tool: string, o: Partial<Omit<Tool, "kind" | "tool">> = {}): Tool => ({ kind: "tool", tool, ...o });
export const Step = (step: string, o: Partial<Omit<Step, "kind" | "step">> = {}): Step => ({ kind: "step", step, ...o });
export const Markdown = (text: string, o: Partial<Omit<Markdown, "kind" | "text">> = {}): Markdown => ({ kind: "markdown", text, ...o });
export const Tab = (title: string, items: ConfigItem[]): Tab => ({ kind: "tab", title, items });
