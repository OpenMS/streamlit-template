export type Column = { name: string; numeric?: boolean };
export type TablePage = { columns: Column[]; rows: any[][]; row_ids: number[]; total: number; unfiltered?: number };

export type FileEntry = { name: string; path: string; size: string; reference: boolean; missing?: boolean };

export type ToppParam = {
  key: string;
  name: string;
  type: "int" | "double" | "string" | "bool" | "int-list" | "double-list" | "string-list";
  value: any;
  default: any;
  valid_strings: string[];
  description: string;
  advanced: boolean;
  included: boolean;
  section: string;
  section_description: string;
  modified: boolean;
  min?: number | null;
  max?: number | null;
};

export type PythonParam = {
  key: string;
  name: string;
  help: string;
  value: any;
  default: any;
  widget_type: string;
  options: any[] | null;
  min: number | null;
  max: number | null;
  step_size: number;
  advanced: boolean;
};
