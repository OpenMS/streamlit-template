"""Convert a Bruker timsTOF .d folder (TDF) to centroided mzML.

Run by CommandExecutor.convert_to_mzml() for every .d input. The frames are
read with timsrust (open source, no Bruker library, wheels for Linux, Windows
and macOS on x86_64 and arm64) and written with pyOpenMS:

- MS1: each frame is summed over ion mobility into one spectrum and
  centroided with OpenMS' PeakPickerHiRes.
- MS2: the PASEF spectra timsrust assembles per precursor (DDA) or per
  isolation window (DIA), already centroided, with their precursor m/z,
  charge, isolation window, collision energy and 1/K0.

Spectra are written in retention time order and numbered scan=1, 2, ...

Only TDF data (analysis.tdf + analysis.tdf_bin) can be read. BAF (maXis,
impact, compact, solariX) and TSF folders fail with an error that says so.
"""
import json
import sys
from pathlib import Path

DEFAULTS = [
    {"key": "in", "value": "", "help": "Bruker .d folder.", "hide": True},
    {"key": "out", "value": "", "help": "Output mzML file.", "hide": True},
]


def bruker_data_kind(path: Path) -> str:
    """Name the raw data format stored in a Bruker .d folder."""
    for kind, marker in (
        ("tdf", "analysis.tdf"),
        ("tsf", "analysis.tsf"),
        ("baf", "analysis.baf"),
    ):
        if Path(path, marker).exists():
            return kind
    return "unknown"


def _ms1_spectrum(frame, metadata, oms, picker):
    import numpy as np

    tof = np.asarray(frame.tof_indices, dtype=np.int64)
    if tof.size == 0:
        mz, intensity = np.empty(0), np.empty(0)
    else:
        # Sum all mobility scans per TOF bin; the bins are the profile points.
        bins, inverse = np.unique(tof, return_inverse=True)
        counts = np.bincount(
            inverse, weights=np.asarray(frame.intensities, dtype=np.float64)
        )
        # PeakPickerHiRes needs a peak to drop to zero on both sides, so empty
        # neighbouring bins are added back with zero intensity.
        neighbours = np.setdiff1d(np.concatenate([bins - 1, bins + 1]), bins)
        neighbours = neighbours[neighbours >= 0]
        all_bins = np.concatenate([bins, neighbours])
        all_counts = np.concatenate([counts, np.zeros(neighbours.size)])
        order = np.argsort(all_bins)
        all_bins, all_counts = all_bins[order], all_counts[order]
        mz = np.asarray(metadata.resolve_mzs(all_bins.astype(np.uint32).tolist()))
        intensity = all_counts * frame.intensity_correction_factor

    profile = oms.MSSpectrum()
    profile.set_peaks((mz, intensity))
    profile.setType(oms.SpectrumSettings.SpectrumType.PROFILE)
    centroided = oms.MSSpectrum()
    picker.pick(profile, centroided)
    centroided.setMSLevel(1)
    centroided.setRT(frame.rt)
    centroided.setType(oms.SpectrumSettings.SpectrumType.CENTROID)
    return centroided


def _ms2_spectrum(spectrum, oms):
    import numpy as np

    out = oms.MSSpectrum()
    out.set_peaks(
        (
            np.asarray(spectrum.mz_values, dtype=np.float64),
            np.asarray(spectrum.intensities, dtype=np.float64),
        )
    )
    out.setMSLevel(2)
    out.setType(oms.SpectrumSettings.SpectrumType.CENTROID)
    precursor = oms.Precursor()
    half_width = spectrum.isolation_width / 2
    precursor.setIsolationWindowLowerOffset(half_width)
    precursor.setIsolationWindowUpperOffset(half_width)
    if spectrum.collision_energy:
        precursor.setActivationEnergy(spectrum.collision_energy)
    precursor.setActivationMethods({oms.Precursor.ActivationMethod.CID})
    p = spectrum.precursor
    if p is not None:
        out.setRT(p.rt)
        precursor.setMZ(p.mz)
        precursor.setDriftTime(p.im)
        if p.charge:
            precursor.setCharge(p.charge)
        if p.intensity:
            precursor.setIntensity(p.intensity)
    else:
        precursor.setMZ(spectrum.isolation_mz)
    out.setPrecursors([precursor])
    return out


def _rt(spectrum) -> float:
    return spectrum.precursor.rt if spectrum.precursor is not None else 0.0


def convert(in_path: str, out_path: str) -> int:
    """Write in_path (.d) as mzML to out_path. Returns the number of spectra."""
    kind = bruker_data_kind(Path(in_path))
    if kind != "tdf":
        names = {
            "baf": "BAF data (maXis, impact, compact, solariX)",
            "tsf": "TSF data (timsTOF without ion mobility, MALDI)",
            "unknown": "a folder without analysis.tdf",
        }
        raise ValueError(
            f"{Path(in_path).name} holds {names[kind]}. Only timsTOF TDF data "
            "can be converted here. Convert it to mzML with ProteoWizard "
            "msconvert and add the mzML instead."
        )

    import pyopenms as oms
    import timsrust_pyo3 as tr

    metadata = tr.Metadata(str(Path(in_path, "analysis.tdf")))
    frames = tr.FrameReader(in_path)
    ms2 = sorted(tr.SpectrumReader(in_path), key=_rt)

    picker = oms.PeakPickerHiRes()
    picker_params = picker.getDefaults()
    picker_params.setValue("signal_to_noise", 0.0)
    picker.setParameters(picker_params)

    consumer = oms.PlainMSDataWritingConsumer(out_path)
    scan = 0

    def write(spec):
        nonlocal scan
        scan += 1
        spec.setNativeID(f"scan={scan}")
        consumer.consumeSpectrum(spec)

    # MS1 frames come in RT order. Each MS2 spectrum is written after the
    # MS1 frame it was acquired after, so FLASHDeconv and other tools that pair
    # an MS2 with the preceding MS1 see the usual order.
    j = 0
    for i in range(len(frames)):
        frame = frames.read_frame(i)
        if frame.ms_level != tr.MSLevel.MS1:
            continue
        while j < len(ms2) and _rt(ms2[j]) < frame.rt:
            write(_ms2_spectrum(ms2[j], oms))
            j += 1
        write(_ms1_spectrum(frame, metadata, oms, picker))
    while j < len(ms2):
        write(_ms2_spectrum(ms2[j], oms))
        j += 1

    # The consumer writes the closing tags when it is destroyed.
    del consumer
    return scan


if __name__ == "__main__":
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        params = json.load(f)
    in_path, out_path = params["in"], params["out"]
    if isinstance(in_path, list):
        in_path = in_path[0]
    if isinstance(out_path, list):
        out_path = out_path[0]
    try:
        n = convert(in_path, out_path)
    except Exception as e:  # reported in the workflow log, not as a traceback
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"Wrote {n} spectra to {out_path}")
