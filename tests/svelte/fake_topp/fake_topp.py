"""
Stand-ins for the two TOPP tools the example workflow calls, for machines
without an OpenMS installation (CI runners, dev boxes with only pyOpenMS).

They are real enough to drive the Svelte app end to end: ``-write_ini``
writes a ParamXML file with the same layout a TOPP tool writes (``Tool:1:...``,
``input file``/``output file`` tags, the algorithm's own defaults and
sections), and a run performs the actual processing through the pyOpenMS
classes the TOPP tools wrap. Never shipped; the tests put this directory on
PATH.

Usage: fake_topp.py <ToolName> [TOPP style arguments]
"""

import sys
from pathlib import Path

import pyopenms as oms


def _algorithm_params(tool: str) -> oms.Param:
    if tool == "FeatureFinderMetabo":
        p = oms.Param()
        p.insert("common:", _common())
        p.insert("mtd:", oms.MassTraceDetection().getDefaults())
        p.insert("epd:", oms.ElutionPeakDetection().getDefaults())
        p.insert("ffm:", oms.FeatureFindingMetabo().getDefaults())
        return p
    if tool == "FeatureLinkerUnlabeledKD":
        return oms.FeatureGroupingAlgorithmKD().getDefaults()
    raise SystemExit(f"unknown tool {tool}")


def _common() -> oms.Param:
    p = oms.Param()
    p.setValue("noise_threshold_int", 10.0, "Intensity threshold below which peaks are regarded as noise.")
    p.setValue("chrom_peak_snr", 3.0, "Minimum signal-to-noise a mass trace should have.")
    p.setValue("chrom_fwhm", 5.0, "Expected chromatographic peak width (in seconds).")
    return p


def write_ini(tool: str, path: str) -> None:
    root = oms.Param()
    prefix = f"{tool}:1:"
    root.setValue(f"{prefix}in", [] if tool == "FeatureLinkerUnlabeledKD" else "", "input file(s)", ["input file"])
    root.setValue(f"{prefix}out", "", "output file", ["output file"])
    for name, value in (("log", ""), ("debug", 0), ("threads", 1), ("no_progress", "false"), ("force", "false"), ("test", "false")):
        root.setValue(f"{prefix}{name}", value, f"Standard TOPP option {name}", ["advanced"])
    root.setValidStrings(f"{prefix}no_progress", ["true", "false"])
    algorithm = _algorithm_params(tool)
    root.insert(f"{prefix}algorithm:", algorithm)
    root.setSectionDescription(f"{prefix}algorithm", "Algorithm parameters section")
    oms.ParamXMLFile().store(path, root)


def parse_args(argv: list[str]) -> dict[str, list[str]]:
    args: dict[str, list[str]] = {}
    key = None
    for a in argv:
        if a.startswith("-") and not _is_number(a):
            key = a[1:]
            args[key] = []
        elif key is not None:
            args[key].append(a)
    return args


def _is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def apply_params(tool: str, args: dict[str, list[str]], algorithm: oms.Param) -> oms.Param:
    for key in algorithm.keys():
        short = "algorithm:" + (key.decode() if isinstance(key, bytes) else key)
        if short not in args:
            continue
        values = args[short]
        default = algorithm.getValue(key)
        if isinstance(default, list):
            algorithm.setValue(key, values)
        elif isinstance(default, int) and not isinstance(default, bool):
            algorithm.setValue(key, int(values[0]))
        elif isinstance(default, float):
            algorithm.setValue(key, float(values[0]))
        else:
            algorithm.setValue(key, values[0] if values else "")
    return algorithm


def run_ffm(args: dict[str, list[str]]) -> None:
    params = apply_params("FeatureFinderMetabo", args, _algorithm_params("FeatureFinderMetabo"))
    exp = oms.MSExperiment()
    oms.MzMLFile().load(args["in"][0], exp)
    exp.sortSpectra(True)
    noise = params.getValue("common:noise_threshold_int")
    mower = oms.ThresholdMower()
    tp = mower.getDefaults()
    tp.setValue("threshold", noise)
    mower.setParameters(tp)
    mower.filterPeakMap(exp)

    mtd = oms.MassTraceDetection()
    mtd.setParameters(params.copy("mtd:", True))
    traces: list = []
    mtd.run(exp, traces, 0)
    epd = oms.ElutionPeakDetection()
    epd.setParameters(params.copy("epd:", True))
    split: list = []
    epd.detectPeaks(traces, split)
    ffm = oms.FeatureFindingMetabo()
    ffm.setParameters(params.copy("ffm:", True))
    fmap = oms.FeatureMap()
    chroms: list = []
    ffm.run(split, fmap, chroms)
    fmap.setUniqueIds()
    fmap.setPrimaryMSRunPath([args["in"][0].encode()])
    Path(args["out"][0]).parent.mkdir(parents=True, exist_ok=True)
    oms.FeatureXMLFile().store(args["out"][0], fmap)
    print(f"FeatureFinderMetabo (pyOpenMS stand-in): {fmap.size()} features")


def run_linker(args: dict[str, list[str]]) -> None:
    params = apply_params("FeatureLinkerUnlabeledKD", args, _algorithm_params("FeatureLinkerUnlabeledKD"))
    maps = []
    for f in args["in"]:
        fm = oms.FeatureMap()
        oms.FeatureXMLFile().load(f, fm)
        maps.append(fm)
    grouper = oms.FeatureGroupingAlgorithmKD()
    grouper.setParameters(params)
    cmap = oms.ConsensusMap()
    headers = cmap.getColumnHeaders()
    for i, f in enumerate(args["in"]):
        h = oms.ColumnHeader()
        h.filename = f
        h.size = maps[i].size()
        h.unique_id = maps[i].getUniqueId()
        headers[i] = h
    cmap.setColumnHeaders(headers)
    grouper.group(maps, cmap)
    cmap.setUniqueIds()
    Path(args["out"][0]).parent.mkdir(parents=True, exist_ok=True)
    oms.ConsensusXMLFile().store(args["out"][0], cmap)
    print(f"FeatureLinkerUnlabeledKD (pyOpenMS stand-in): {cmap.size()} consensus features")


def main(argv: list[str]) -> int:
    tool, rest = argv[0], argv[1:]
    if "-write_ini" in rest:
        write_ini(tool, rest[rest.index("-write_ini") + 1])
        return 0
    if "--help" in rest:
        print(f"{tool} -- pyOpenMS stand-in\nVersion: {oms.__version__}-fake")
        return 0
    args = parse_args(rest)
    if tool == "FeatureFinderMetabo":
        run_ffm(args)
    elif tool == "FeatureLinkerUnlabeledKD":
        run_linker(args)
    else:
        print(f"unknown tool {tool}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
