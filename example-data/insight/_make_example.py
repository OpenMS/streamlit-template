"""Generate small parquet fixtures for the Linked Grid Demo page.

Run once to (re)create the ``.parquet`` files committed alongside this script::

    python example-data/insight/_make_example.py

The fixtures are intentionally tiny and hand-built, shaped like OpenMS-Insight's own test
fixtures (a few scans / peaks / a sequence), but with enough rows to exercise the
Table <-> LinePlot <-> Heatmap <-> SequenceView cross-linking on the demo page:

- ``spectra.parquet``   master table   : scan_id, rt, ms_level, precursor_mz, n_peaks
- ``peaks.parquet``     per-peak long  : scan_id, peak_id, mass, intensity, is_annotated, ion_label
- ``heat.parquet``      peak map       : scan_id, rt, mass, intensity, peak_id
- ``sequences.parquet`` per-scan seq   : scan_id, sequence, precursor_charge

IDs are stable and dataset-scoped: ``scan_id`` 0..N-1, ``peak_id`` globally unique across all
scans so a peak click selects exactly one peak. The same ``peak_id`` values are reused in
``heat.parquet`` so a heatmap click cross-links to the spectrum/sequence panels.
"""

import math
from pathlib import Path

import polars as pl

HERE = Path(__file__).resolve().parent

# A handful of one-letter sequences (only a few scans carry a sequence, per the plan).
SEQUENCES = {
    1: ("PEPTIDEK", 2),
    3: ("ACDEFGHIK", 3),
    7: ("MNQRSTVWYK", 2),
}

N_SCANS = 20
PEAKS_PER_SCAN = 20  # -> 400 peak rows total


def _amino_acid_masses():
    # Monoisotopic residue masses (Da) for fragment-like peak generation.
    return {
        "A": 71.03711, "C": 103.00919, "D": 115.02694, "E": 129.04259,
        "F": 147.06841, "G": 57.02146, "H": 137.05891, "I": 113.08406,
        "K": 128.09496, "L": 113.08406, "M": 131.04049, "N": 114.04293,
        "P": 97.05276, "Q": 128.05858, "R": 156.10111, "S": 87.03203,
        "T": 101.04768, "V": 99.06841, "W": 186.07931, "Y": 163.06333,
    }


def build():
    aa = _amino_acid_masses()

    spectra_rows = []
    peak_rows = []
    heat_rows = []
    seq_rows = []

    peak_id = 0  # globally unique across scans (the cross-link click target)

    for scan_id in range(N_SCANS):
        rt = round(1.0 + scan_id * 0.5, 4)
        ms_level = 1 if scan_id % 4 == 0 else 2
        precursor_mz = round(400.0 + scan_id * 13.37, 4)

        # Build this scan's peaks. If the scan has a sequence, lay down b-ion-like
        # neutral masses for the first few peaks so the SequenceView fragment matching
        # has something to annotate; fill the rest with deterministic synthetic peaks.
        seq_info = SEQUENCES.get(scan_id)
        annotated_masses = []
        annotated_labels = []
        if seq_info is not None:
            sequence, charge = seq_info
            seq_rows.append(
                {"scan_id": scan_id, "sequence": sequence, "precursor_charge": charge}
            )
            running = 0.0
            for i, ch in enumerate(sequence[:-1]):
                running += aa.get(ch, 110.0)
                # b-ion neutral mass approximation (sum of residues; close enough for a fixture)
                annotated_masses.append(round(running + 1.00794, 4))
                annotated_labels.append(f"b{i + 1}")

        for j in range(PEAKS_PER_SCAN):
            if j < len(annotated_masses):
                mass = annotated_masses[j]
                intensity = round(5000.0 - j * 137.0 + scan_id * 11.0, 2)
                is_annotated = 1
                ion_label = annotated_labels[j]
            else:
                # deterministic synthetic peak
                mass = round(150.0 + j * 97.3 + scan_id * 1.7, 4)
                intensity = round(
                    1000.0 * (1.0 + math.sin(j * 0.7 + scan_id * 0.3)) + 200.0, 2
                )
                is_annotated = 0
                ion_label = ""

            peak_rows.append(
                {
                    "scan_id": scan_id,
                    "peak_id": peak_id,
                    "mass": mass,
                    "intensity": max(intensity, 1.0),
                    "is_annotated": is_annotated,
                    "ion_label": ion_label,
                }
            )
            # Peak map row: reuse peak_id + scan_id so a heatmap click cross-links.
            heat_rows.append(
                {
                    "scan_id": scan_id,
                    "rt": rt,
                    "mass": mass,
                    "intensity": max(intensity, 1.0),
                    "peak_id": peak_id,
                }
            )
            peak_id += 1

        spectra_rows.append(
            {
                "scan_id": scan_id,
                "rt": rt,
                "ms_level": ms_level,
                "precursor_mz": precursor_mz,
                "n_peaks": PEAKS_PER_SCAN,
            }
        )

    spectra = pl.DataFrame(
        spectra_rows,
        schema={
            "scan_id": pl.Int64,
            "rt": pl.Float64,
            "ms_level": pl.Int64,
            "precursor_mz": pl.Float64,
            "n_peaks": pl.Int64,
        },
    )
    peaks = pl.DataFrame(
        peak_rows,
        schema={
            "scan_id": pl.Int64,
            "peak_id": pl.Int64,
            "mass": pl.Float64,
            "intensity": pl.Float64,
            "is_annotated": pl.Int64,
            "ion_label": pl.Utf8,
        },
    )
    heat = pl.DataFrame(
        heat_rows,
        schema={
            "scan_id": pl.Int64,
            "rt": pl.Float64,
            "mass": pl.Float64,
            "intensity": pl.Float64,
            "peak_id": pl.Int64,
        },
    )
    sequences = pl.DataFrame(
        seq_rows,
        schema={
            "scan_id": pl.Int64,
            "sequence": pl.Utf8,
            "precursor_charge": pl.Int64,
        },
    )

    spectra.write_parquet(HERE / "spectra.parquet")
    peaks.write_parquet(HERE / "peaks.parquet")
    heat.write_parquet(HERE / "heat.parquet")
    sequences.write_parquet(HERE / "sequences.parquet")

    print(
        f"Wrote fixtures to {HERE}:\n"
        f"  spectra.parquet   {spectra.height} rows\n"
        f"  peaks.parquet     {peaks.height} rows\n"
        f"  heat.parquet      {heat.height} rows\n"
        f"  sequences.parquet {sequences.height} rows"
    )


if __name__ == "__main__":
    build()
