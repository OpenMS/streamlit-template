// src/python-tools/export_consensus_feature_df.py: the consensus features of a
// consensusXML file as a table next to it (.tsv), one intensity column per file.

import type { StepDef } from "../lib/workflow/step";
import { basename } from "../lib/storage/store";

const round = (x: number, d: number) => Math.round(x * 10 ** d) / 10 ** d;

export const export_consensus_feature_df: StepDef = {
  name: "export_consensus_feature_df",
  DEFAULTS: [{ key: "in", value: "", help: "Input consensusXML file.", hide: true }],
  async run({ O, store }, params) {
    const path: string = Array.isArray(params.in) ? params.in[0] : params.in;
    const bytes = await store.read(path);
    if (!bytes) throw new Error(`File not found: ${path}`);
    const local = "/work/export.consensusXML";
    O.FS.writeFile(local, bytes);
    const cm = new O.ConsensusMap();
    const file = new O.ConsensusXMLFile();
    let features, headers;
    try {
      file.load(local, cm);
      features = cm.toArray();
      headers = cm.getColumnHeaders().sort((a, b) => a.index - b.index);
    } finally {
      file.delete();
      cm.delete();
      O.FS.unlink(local);
    }
    const columns = ["metabolite", "charge", "rt", "mz", "quality", ...headers.map((h) => basename(h.filename))];
    const lines = [columns.join("\t")];
    for (const f of features) {
      const intensities = headers.map((h) => f.elements.find((e) => e.mapIndex === h.index)?.intensity ?? 0);
      lines.push([`${round(f.mz, 4)}@${round(f.rt, 2)}`, f.charge, f.rt, f.mz, f.quality, ...intensities].join("\t"));
    }
    await store.write(path.replace(/\.[^./]*$/, ".tsv"), `${lines.join("\n")}\n`);
  },
};
