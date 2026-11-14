// The pyOpenMS toolbox pages, on the OpenMS WebAssembly module: ports of
// src/peptide_mz_calculator.py, utils/digest.py + utils/fasta.py,
// content/isotope_pattern_generator.py and content/fragmentation.py, returning the same values.

import { scoped, type OpenMS } from "../openms";

const PROTON = 1.007276;

export class InputError extends Error {}

// ------------------------------------------------------------ m/z calculator

export function peptideMz(O: OpenMS, sequence: string, minCharge = 1, maxCharge = 4) {
  sequence = sequence.trim();
  if (!sequence) throw new InputError("Sequence cannot be empty");
  if (minCharge < 1 || maxCharge < minCharge) throw new InputError("Charge range must be positive and ascending");
  return scoped((keep) => {
    let seq;
    try {
      seq = keep(O.AASequence.fromString(sequence));
    } catch (e: any) {
      throw new InputError(`Invalid sequence format: ${e.message}`);
    }
    const unmodified = seq.toUnmodifiedString();
    const composition: Record<string, number> = {};
    for (const aa of unmodified) composition[aa] = (composition[aa] ?? 0) + 1;
    const base = {
      monoisotopic_mass: seq.getMonoWeight(),
      molecular_formula: keep(seq.getFormula()).toString(),
      sequence_length: unmodified.length,
      aa_composition: composition,
    };
    const charge_results: Record<number, { mz_ratio: number; charge_state: number }> = {};
    for (let z = minCharge; z <= maxCharge; z++) charge_results[z] = { mz_ratio: seq.getMZ(z), charge_state: z };
    return { ...base, ...charge_results[minCharge], charge_results, charge_range: [minCharge, maxCharge] };
  });
}

// ---------------------------------------------------------------- digest

export function parseFasta(text: string): [string, string][] {
  const out: [string, string][] = [];
  let header: string | null = null;
  let seq: string[] = [];
  const flush = () => {
    if (header === null) return;
    if (!seq.length) throw new InputError(`Empty sequence found for header: ${header}`);
    out.push([header, seq.join("")]);
  };
  text
    .trim()
    .split("\n")
    .forEach((raw, i) => {
      const line = raw.trim();
      if (!line) return;
      if (line.startsWith(">")) {
        flush();
        header = line.slice(1);
        seq = [];
      } else {
        if (header === null) throw new InputError(`Line ${i + 1}: Sequence data found before header`);
        seq.push(line.toUpperCase());
      }
    });
  flush();
  if (!out.length) throw new InputError("No valid FASTA sequences found");
  for (const [h, s] of out) {
    const bad = [...new Set(s.replace(/[ACDEFGHIKLMNPQRSTVWY]/g, ""))].sort();
    if (bad.length) throw new InputError(`Invalid amino acids found in sequence '${accession(h)}': ${bad.join(", ")}`);
  }
  return out;
}

export function accession(header: string): string {
  const uni = header.match(/^(sp|tr)\|([^|]+)\|/);
  if (uni) return uni[2];
  const ncbi = header.match(/^(?:gi\|\d+\|)?(?:ref\|)?([^|]+)/);
  if (ncbi) return ncbi[1];
  return header.split(/\s+/)[0] || header;
}

export function description(header: string): string {
  const uni = header.match(/^(sp|tr)\|[^|]+\|[^|\s]+\s*(.*)/);
  if (uni) return uni[2].trim();
  const i = header.indexOf(" ");
  return i >= 0 ? header.slice(i + 1).trim() : header;
}

export const enzymes = (O: OpenMS) => O.ProteaseDB.getAllNames();

export type DigestRequest = {
  fasta: string;
  enzyme?: string;
  missed_cleavages?: number;
  max_charges?: number;
  min_length?: number;
  max_length?: number;
};

export function digest(O: OpenMS, r: DigestRequest) {
  const { enzyme = "Trypsin", missed_cleavages = 2, max_charges = 4, min_length = 6, max_length = 50 } = r;
  const sequences = parseFasta(r.fasta);
  const columns = ["Accession", "Description", "Peptide Sequence", "Length", "Start", "End", "[M]"];
  for (let z = 1; z <= max_charges; z++) columns.push(`[M + ${z}H]`);
  const rows: (string | number)[][] = [];
  const coverage: Record<string, { sequence: string; coverage: number[]; description: string }> = {};
  for (const [header, sequence] of sequences) coverage[accession(header)] = { sequence, coverage: new Array(sequence.length).fill(0), description: "" };

  scoped((keep) => {
    const d = keep(new O.ProteaseDigestion());
    d.setEnzyme(enzyme);
    d.setMissedCleavages(missed_cleavages);
    for (const [header, sequence] of sequences) {
      const acc = accession(header);
      const desc = description(header);
      const peptides = d.digest(keep(O.AASequence.fromString(sequence)), 1, sequence.length);
      for (const p of peptides) {
        keep(p);
        const pep = p.toString();
        if (!pep || pep.length < min_length || pep.length > max_length) continue;
        const mass = p.getMonoWeight();
        const starts: number[] = [];
        for (let pos = sequence.indexOf(pep); pos !== -1; pos = sequence.indexOf(pep, pos + 1)) starts.push(pos);
        const row: (string | number)[] = [
          acc,
          desc,
          pep,
          pep.length,
          starts.map((s) => s + 1).join(","),
          starts.map((s) => s + pep.length).join(","),
          round(mass, 4),
        ];
        for (let z = 1; z <= max_charges; z++) row.push(round((mass + z * PROTON) / z, 4));
        rows.push(row);
        const cov = coverage[acc];
        if (!cov.description) cov.description = desc;
        for (const s of starts) for (let i = s; i < s + pep.length; i++) cov.coverage[i]++;
      }
    }
  });

  const masses = rows.map((r) => r[6] as number);
  const stats = rows.length
    ? {
        total_peptides: rows.length,
        unique_proteins: new Set(rows.map((r) => r[0])).size,
        avg_peptide_length: rows.reduce((a, r) => a + (r[3] as number), 0) / rows.length,
        mass_range: [Math.min(...masses), Math.max(...masses)],
      }
    : {};
  return { n_sequences: sequences.length, stats, table: { columns, rows }, coverage: rows.length ? coverage : {} };
}

// ------------------------------------------------------------ isotope pattern

export type IsotopeRequest = { method: "formula" | "peptide" | "oligonucleotide" | "mass"; value: string; fine?: boolean };

export function isotopePattern(O: OpenMS, { method, value, fine = false }: IsotopeRequest) {
  const generatorName = fine ? "Fine" : "Coarse";
  return scoped((keep) => {
    const generator = keep(fine ? new O.FineIsotopePatternGenerator() : new O.CoarseIsotopePatternGenerator());
    const pattern = (formula: ReturnType<OpenMS["EmpiricalFormula"]["fromString"]>) => {
      const peaks = keep(formula.getIsotopeDistribution(generator)).getPeaks();
      return { mzs: [...peaks.mz], intensities: [...peaks.intensity] };
    };
    if (method === "formula") {
      const f = value.trim();
      if (!f) throw new InputError("Formula cannot be empty");
      let formula;
      try {
        formula = keep(O.EmpiricalFormula.fromString(f));
      } catch (e: any) {
        throw new InputError(`Invalid formula format: ${e.message}`);
      }
      return {
        ...pattern(formula),
        monoisotopic_mass: formula.getMonoWeight(),
        average_mass: formula.getAverageWeight(),
        formula: f,
        source_type: `Elemental Formula (${generatorName})`,
        input_value: f,
        generator: generatorName,
      };
    }
    if (method === "peptide") {
      const clean = value.trim().toUpperCase().replace(/[^ACDEFGHIKLMNPQRSTVWYXU]/g, "");
      if (!value.trim()) throw new InputError("Sequence cannot be empty");
      if (!clean) throw new InputError("No valid amino acid letters found");
      const seq = keep(O.AASequence.fromString(clean));
      const formula = keep(seq.getFormula());
      return {
        ...pattern(formula),
        monoisotopic_mass: seq.getMonoWeight(),
        average_mass: seq.getAverageWeight(),
        formula: formula.toString(),
        sequence: clean,
        source_type: `Peptide/Protein Sequence (${generatorName})`,
        input_value: value,
        generator: generatorName,
      };
    }
    if (method === "mass") {
      const target = Number(value);
      if (!Number.isFinite(target)) throw new InputError("Mass must be a number");
      if (target <= 0) throw new InputError("Mass must be greater than 0");
      return isotopeFromMass(O, target);
    }
    // NASequence is not part of the WebAssembly bindings
    throw new InputError("Oligonucleotide sequences are not supported by the OpenMS WebAssembly build yet.");
  });
}

/** Port of generate_isotope_pattern_from_mass: the averagine pattern whose most abundant peak is at the mass */
function isotopeFromMass(O: OpenMS, target: number) {
  return scoped((keep) => {
    const gen = keep(new O.CoarseIsotopePatternGenerator());
    const apex = (m: number) => keep(gen.estimateFromPeptideWeight(m)).getMostAbundant()!.mz;
    const start = apex(target);
    const samples = [start];
    const masses = [target];
    for (const sign of [1, -1]) {
      for (let delta = 0; delta < 20; delta += 0.2) {
        const s = apex(target + sign * delta);
        samples.push(s);
        masses.push(target + sign * delta);
        if (Math.abs(s - target) > Math.abs(start - target)) break;
      }
    }
    let best = 0;
    samples.forEach((s, i) => {
      if (Math.abs(s - target) < Math.abs(samples[best] - target)) best = i;
    });
    const dist = keep(gen.estimateFromPeptideWeight(masses[best]));
    const peaks = dist.getPeaks();
    const shift = dist.getMostAbundant()!.mz - target;
    const mzs = [...peaks.mz].map((m) => m - shift);
    const intensities = [...peaks.intensity];
    const average = [...peaks.mz].reduce((a, m, i) => a + m * intensities[i], 0) - shift;
    return {
      mzs,
      intensities,
      monoisotopic_mass: Math.min(...mzs),
      average_mass: average,
      formula: "Estimated from mass",
      source_type: "Mass Estimation",
      input_value: `${target.toFixed(2)} Da`,
    };
  });
}

// ------------------------------------------------------------- fragment ions

export const ION_TYPES: Record<string, { name: string; description: string; param: string }> = {
  a: { name: "a-ions", description: "N-terminal ions (peptide bond + loss of CO)", param: "add_a_ions" },
  b: { name: "b-ions", description: "N-terminal ions (peptide bond cleavage)", param: "add_b_ions" },
  c: { name: "c-ions", description: "N-terminal ions (N-Cα bond cleavage)", param: "add_c_ions" },
  x: { name: "x-ions", description: "C-terminal ions (N-Cα bond + addition of CO)", param: "add_x_ions" },
  y: { name: "y-ions", description: "C-terminal ions (peptide bond cleavage)", param: "add_y_ions" },
  z: { name: "z-ions", description: "C-terminal ions (N-Cα bond cleavage)", param: "add_z_ions" },
};

export function fragments(O: OpenMS, sequence: string, ionTypes: string[] = ["b", "y"], charges: number[] = [1]) {
  const clean = sequence.trim().toUpperCase().replace(/[^ACDEFGHIKLMNPQRSTVWYXU]/g, "");
  if (!sequence.trim()) throw new InputError("Sequence cannot be empty");
  if (!clean) throw new InputError("No valid amino acid letters found");
  if (clean.length < 2) throw new InputError("Sequence must be at least 2 amino acids long for fragmentation");
  if (!ionTypes.length) throw new InputError("Please select at least one ion type");
  if (!charges.length) throw new InputError("Please select at least one charge state");

  const rows: [number, number, number, string, number, string, string][] = [];
  scoped((keep) => {
    const seq = keep(O.AASequence.fromString(clean));
    const tsg = keep(new O.TheoreticalSpectrumGenerator());
    const values: Record<string, boolean | number> = { add_first_prefix_ion: true, add_losses: false, add_metainfo: true, max_isotope: 2 };
    for (const [k, t] of Object.entries(ION_TYPES)) values[t.param] = ionTypes.includes(k);
    tsg.setParameterValues(values);
    for (const z of charges) {
      const spec = keep(new O.MSSpectrum());
      tsg.getSpectrum(spec, seq, z, z);
      const { mz, intensity } = spec.getPeaks();
      const ann = spec.getStringDataArrays()[0]?.data ?? [];
      mz.forEach((m, i) => {
        const a = ann[i] ?? "";
        const match = a.match(/^([abcxyz])(\d+)(\+*)/);
        const ion = match ? match[1] : "unknown";
        const n = match ? Number(match[2]) : 0;
        const frag = !match || n > clean.length ? "" : "abc".includes(ion) ? clean.slice(0, n) : clean.slice(-n);
        rows.push([m, intensity[i], z, ion, n, frag, a || `m/z ${m.toFixed(4)}`]);
      });
    }
  });
  rows.sort((a, b) => a[3].localeCompare(b[3]) || a[4] - b[4] || a[2] - b[2]);
  return {
    sequence: clean,
    ion_types: ionTypes,
    charges,
    fragments: { columns: ["mz", "intensity", "charge", "ion_type", "fragment_number", "sequence", "annotation"], rows },
  };
}

const round = (x: number, d: number) => Math.round(x * 10 ** d) / 10 ** d;
