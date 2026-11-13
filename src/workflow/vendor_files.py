"""Vendor MS data (Thermo .raw, Bruker .d) in workflow inputs.

Kept free of Streamlit so the queue worker can import it.
"""
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import List, Union


# Vendor formats convert_to_mzml() converts. A Bruker .d is a folder.
VENDOR_FORMATS = ["raw", "d"]


def vendor_format(path) -> str:
    """Returns "raw" or "d" for a vendor file that needs conversion, else None."""
    suffix = Path(path).suffix.lower().lstrip(".")
    return suffix if suffix in VENDOR_FORMATS else None


# FileConverter's reader for Thermo .raw files. OpenMS 3.6 offers two:
# "inprocess" (its built-in reader, openms-thermo-bridge on a .NET 8 or newer
# runtime) and "external" (ThermoRawFileParser, on the .NET Framework on
# Windows and on mono elsewhere). The two write slightly different mzML, and
# each platform defaults to another one, so convert_to_mzml() names the
# built-in reader wherever the installed FileConverter has it: the same .raw
# file then gives the same mzML in the Docker image and every desktop app.
THERMO_READER = "inprocess"


def _thermo_reader_item(ini_path):
    """The ``RawToMzML:reader`` ITEM of a FileConverter .ini, or None."""
    try:
        root = ET.parse(ini_path).getroot()
    except (OSError, ET.ParseError):
        return None
    for node in root.iter("NODE"):
        if node.get("name") != "RawToMzML":
            continue
        for item in node.findall("ITEM"):
            if item.get("name") == "reader":
                return item
    return None


def thermo_default_reader(ini_path):
    """FileConverter's own default Thermo reader in the .ini at ini_path
    (``external``, ThermoRawFileParser, on Windows), or None without one."""
    item = _thermo_reader_item(ini_path)
    return (item.get("value") or None) if item is not None else None


def thermo_reader_available(ini_path) -> bool:
    """True when the FileConverter .ini at ini_path offers THERMO_READER.

    Reads ``RawToMzML:reader`` and its valid strings. An OpenMS before 3.6
    (no such parameter) or one built without the built-in reader
    (``WITH_THERMO_RAW=OFF``, valid strings ``external`` only) answers False.
    """
    item = _thermo_reader_item(ini_path)
    if item is None:
        return False
    allowed = (item.get("restrictions") or "").split(",")
    return THERMO_READER in [a.strip() for a in allowed]


def extract_bruker_zip(archive, files_dir: Path) -> List[str]:
    """Unpack the Bruker .d folder(s) in a zip archive into files_dir.

    A browser cannot upload a folder, so online users upload a .d zipped. The
    archive may hold one or more ``<name>.d/`` folders, or the contents of a
    single one (then it is named after the archive, ``run.d.zip`` -> ``run.d``).
    Members outside the .d folders and paths escaping files_dir are skipped.

    Returns:
        List[str]: The names of the .d folders that were added.
    """
    files_dir = Path(files_dir).resolve()
    with zipfile.ZipFile(archive) as zf:
        members = [m for m in zf.infolist() if not m.is_dir()]
        tops = {Path(m.filename).parts[0] for m in members if len(Path(m.filename).parts) > 1}
        d_tops = {t for t in tops if t.lower().endswith(".d")}
        # An UploadedFile carries the browser's file name; a path is its own.
        archive_name = Path(
            archive if isinstance(archive, (str, Path)) else getattr(archive, "name", "upload.zip")
        ).name
        added = set()
        for m in members:
            parts = Path(m.filename).parts
            if d_tops:
                if len(parts) < 2 or parts[0] not in d_tops:
                    continue
                folder, rel = parts[0], parts[1:]
            else:
                stem = archive_name[: -len(".zip")] if archive_name.lower().endswith(".zip") else archive_name
                folder = stem if stem.lower().endswith(".d") else f"{stem}.d"
                rel = parts
            target = Path(files_dir, folder, *rel).resolve()
            if files_dir not in target.parents:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(m) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            added.add(folder)
    return sorted(added)


def has_type(path: Union[Path, str], file_types: List[str]) -> bool:
    """True if the file (or .d folder) name ends with one of the extensions, ignoring case."""
    name = Path(path).name.lower()
    return any(name.endswith(f".{ft.lower()}") for ft in file_types)
