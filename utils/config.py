"""
Configuration constants for the digest functionality.
"""

# List of enzymes supported by pyOpenMS
OPENMS_SUPPORTED_ENZYMES = [
    "Trypsin",
    "Arg-C",
    "Asp-N",
    "Asp-N_ambic",
    "Chymotrypsin",
    "CNBr",
    "Formic_acid",
    "Lys-C",
    "Lys-N",
    "PepsinA",
    "TrypChymo",
    "Trypsin/P",
    "V8-DE",
    "V8-E",
    "leukocyte elastase",
    "proline endopeptidase",
    "glutamyl endopeptidase",
    "Alpha-lytic protease",
    "2-iodobenzoate",
    "iodosobenzoate",
    "staphylococcal protease/D",
    "proline-endopeptidase/HKR",
    "Glu-C+P",
    "PepsinA + P",
    "cyanogen-bromide",
    "Clostripain/P",
    "elastase-trypsin-chymotrypsin",
    "no cleavage",
    "unspecific cleavage",
    "Trypsin_P"
]

# Default values
DEFAULT_ENZYME = "Trypsin"
DEFAULT_MISSED_CLEAVAGES = 2
DEFAULT_MAX_CHARGES = 5