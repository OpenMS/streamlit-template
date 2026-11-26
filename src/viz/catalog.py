"""Every component of the visualization library, by folder, with what it shows.

An app lists the components it offers in its own Viewer catalog; this one says
which library module draws each of them. ``tests/test_viz_catalog.py`` checks
that every module in a folder is listed here and every entry has a module.
"""

from __future__ import annotations

FOLDERS = {
    "ms_data": "MS data",
    "features": "Features and masses",
    "identification": "Identification",
    "quantification": "Quantification",
}

# name, folder, label, entry point, description
_ENTRIES = [
    ('scan_table', 'ms_data', 'Scan table', 'settings',
     'One row per spectrum of a run, with its scan number, MS level, retention time, precursor mass and how many masses it holds. A click selects the spectrum.'),
    ('raw_heatmap', 'ms_data', 'Raw heatmap', 'settings',
     'The peaks of one MS level by retention time and m/z, coloured by log intensity, downsampled in levels so a whole run draws at once. A click selects the spectrum.'),
    ('peak_map_3d', 'ms_data', '3D peak map', 'settings',
     'The MS1 peaks of a run by m/z, retention time and intensity, the strongest peaks of each spectrum; the precursor spectrum of the selected spectrum drawn apart.'),
    ('chromatogram', 'ms_data', 'Chromatogram', 'settings',
     'Total ion current, base peak and deconvolved intensity of one MS level over retention time. A click selects the spectrum.'),
    ('spectrum', 'ms_data', 'Raw spectrum', 'settings',
     "The peaks of the selected spectrum, those of a deconvolved mass marked, with the picked mass's isotope envelope and the fragment ions a sequence view matched."),
    ('precursor_spectrum', 'ms_data', 'Precursor spectrum', 'settings',
     "The MS1 spectrum the selected fragmentation spectrum's precursor was picked from, its precursor mass marked and the isolated m/z range shaded."),
    ('acquisition_map', 'ms_data', 'Acquisition decisions', 'settings',
     'The masses of every survey scan by retention time and mass, the precursors an intelligent acquisition chose and identified drawn over them. A click picks the precursor.'),
    ('chosen_precursors', 'ms_data', 'Chosen precursors', 'settings',
     'Every precursor an intelligent acquisition chose, with its mass, charge, quality score, the scans commanded for it and, once identified, its proteoform. A click picks the precursor.'),
    ('commanded_scans', 'ms_data', 'Commanded scans', 'settings',
     'The MS2 and MS3 scans commanded for the picked precursor, with their status, purpose, isolation, energy, exploration variant and what was found in them.'),
    ('mass_table', 'features', 'Mass table', 'settings',
     'The deconvolved masses of the selected spectrum with their intensity, charge and isotope range, isotope cosine, S/N and quality score. A click picks the mass.'),
    ('deconvolved_spectrum', 'features', 'Deconvolved spectrum', 'settings',
     'The masses of the selected spectrum as sticks, the picked one highlighted, with the fragment ions a sequence view matched.'),
    ('deconvolved_heatmap', 'features', 'Deconvolved heatmap', 'settings',
     'The masses of one MS level by retention time and monoisotopic mass, coloured by log intensity. A click selects the spectrum and the mass.'),
    ('signal_noise_3d', 'features', 'Signal and noise (3D)', 'settings',
     '3D S/N plot: the signal and noise peaks of the picked mass (the precursor while none is picked) by mass, charge and intensity.'),
    ('isotope_envelope', 'features', 'Isotope envelope', 'settings',
     'The observed isotope envelope of the picked mass (all charges summed; the precursor while no mass is picked) above the averagine envelope of that mass.'),
    ('precursor_xic', 'features', 'Precursor XIC', 'settings',
     'The precursor mass of the selected fragmentation spectrum traced over the MS1 spectra, one line per charge and their sum.'),
    ('qscore_fdr', 'features', 'QScore FDR', 'settings',
     'The density of the quality scores of target and decoy masses, from which the mass-level FDR is estimated.'),
    ('run_qc', 'features', 'Run QC', 'settings',
     "Small plots of a run's masses: the QScore, charge and mass distributions and the masses found per spectrum over retention time."),
    ('prsm_table', 'identification', 'PrSM table', 'settings',
     'Every proteoform-spectrum match of a run with its scan, protein, characterization, matched fragments, score and q-values; a button per row opens the whole row. A click picks the PrSM and its spectrum.'),
    ('protein_groups', 'identification', 'Protein groups', 'settings',
     'One row per identified protein with its proteoform and PrSM counts, best score and q-values. A click picks the protein; the proteoform table lists its proteoforms.'),
    ('proteoforms', 'identification', 'Proteoforms', 'settings',
     'The proteoforms of the picked protein with their mass shifts, PrSM count, best score and q-values. A click picks the proteoform and its best PrSM.'),
    ('proteoform_prsms', 'identification', 'PrSMs of a proteoform', 'settings',
     'Every spectrum matched to the picked proteoform with its fragments, score and q-values. A click picks the PrSM and its spectrum.'),
    ('prsm_mass_table', 'identification', 'PrSM mass table', 'settings',
     "Every deconvolved mass of the picked PrSM's spectrum and the fragment ion it explains, with its mass errors; a toggle shows matched masses only. A row picks its mass."),
    ('tag_table', 'identification', 'Tag table', 'settings',
     'The tags of the selected spectrum with their position in the protein, sequence, score and flanking masses, sorted by score. Picking a residue lists the tags covering it; a click picks the tag.'),
    ('tag_spectrum', 'identification', 'Tag spectrum', 'settings',
     'The deconvolved masses of the selected spectrum with the picked sequence tag drawn as a ladder of residues over them.'),
    ('sequence_view', 'identification', 'Sequence view', 'settings',
     "The proteoform's sequence with its modifications and the fragment ions that cover each bond, the matched fragments listed below. For a run that was not identified, a sequence the user sets is matched against the selected spectrum. Picking a residue, mass or fragment is shared with the other components."),
    ('structure_view', 'identification', 'Structure view', 'settings',
     "The predicted 3D structure of the picked proteoform's protein, its residues coloured by the fragments that cover them. Picking a residue or fragment is shared with the sequence view."),
    ('fragment_errors', 'identification', 'Fragment mass errors', 'settings',
     "The error of each matched fragment of the picked identification over its mass, coloured by ion type, with the tolerance as lines; a click can pick the residue next to the fragment's bond."),
    ('score_distribution', 'identification', 'Identification scores', 'settings',
     'The score distribution of the identified proteoforms, targets and, when the search kept them, decoys.'),
    ('proteoform_heatmap', 'identification', 'Proteoform map', 'settings',
     'Every PrSM as a point at its retention time and proteoform mass, coloured by score. A click picks the PrSM in the protein, proteoform and PrSM tables; a box or lasso picks the proteins of the PrSMs in it.'),
    ('mass_shift_histogram', 'identification', 'Mass shift histogram', 'settings',
     'How many identifications (PSMs or PrSMs) carry each mass shift, the recurring shifts labelled with the modification they match. A click picks the shift, which narrows the tables that filter on it to the rows carrying it.'),
    ('mass_shift_table', 'identification', 'Mass shifts', 'settings',
     'The recurring precursor mass shifts with how many identifications carry each (and, for proteoforms, how many proteoforms), the Unimod modifications they match and how far off they are. Clicking a shift picks it, clicking it again unpicks it.'),
    ('mass_shift_matches', 'identification', 'Identifications of a mass shift', 'settings',
     'The identifications (PSMs or PrSMs) carrying the picked mass shift: sequence, mass difference, charge, m/z, retention time, score and file.'),
    ('psm_table', 'identification', 'PSM table', 'settings',
     'Every peptide-spectrum match of a run with its peptide, proteins, charge, m/z, retention time, score and q-value; filters for q-value and contaminants and a search over peptides and proteins. A click picks the PSM and its spectrum.'),
    ('psm_map', 'identification', 'PSM map', 'settings',
     'Every PSM as a point at its retention time and m/z, coloured by score. A click picks the PSM in the table and the spectrum components.'),
    ('peptide_sequence_view', 'identification', 'Peptide sequence view', 'settings',
     'The peptide of the picked PSM with its fragment ions matched in the spectrum (b/y and other ion types, neutral losses) marked on the residues; a click on a fragment picks its peak.'),
    ('annotated_spectrum', 'identification', 'Annotated spectrum', 'settings',
     'The spectrum of the picked PSM with the fragments the sequence view matched labelled and coloured by ion type.'),
    ('predicted_spectrum', 'identification', 'Measured and predicted spectrum', 'settings',
     'The measured spectrum of the picked PSM above, the spectrum predicted for its peptide mirrored below, the matched fragments labelled on both.'),
    ('precursor_mass_error', 'identification', 'Precursor mass error', 'settings',
     'How the precursor mass errors (ppm) of the PSMs are distributed, targets and decoys apart.'),
    ('protein_table', 'identification', 'Protein table', 'settings',
     'The identified proteins with their coverage, peptide and PSM counts and the replicates they were found in; contaminants hidden by a toggle, a search over accession, gene and name. A click picks the protein.'),
    ('protein_peptides', 'identification', 'Peptides of a protein', 'settings',
     'The peptides of the picked protein with their PSM counts; a click picks the peptide.'),
    ('protein_psms', 'identification', 'PSMs of a protein', 'settings',
     'The PSMs of the picked protein and peptide with charge, m/z, retention time and score; a click picks the PSM.'),
    ('sequence_coverage', 'identification', 'Sequence coverage', 'settings',
     'The reference sequence in blocks with every identified oligonucleotide or peptide as a bar under the residues it covers, one track per group, coloured by how often it was identified and its modified residues marked. A click picks the match.'),
    ('fragment_spectrum', 'identification', 'Fragment spectrum', 'settings',
     'The peaks of the picked spectrum, those assigned to a fragment ion labelled and coloured by ion series; a clicked peak or fragment is drawn gold.'),
    ('fragment_table', 'identification', 'Fragment ions', 'settings',
     'The fragment ions assigned in the picked spectrum with series, observed and expected m/z, error and intensity. A click picks the peak.'),
    ('identification_qc', 'identification', 'Identification QC', 'settings',
     "Small plots of a run's identifications: PrSMs per minute over retention time, sequence coverage and the median fragment mass error over retention time."),
    ('identifications_per_run', 'identification', 'Identifications per run', 'settings',
     'Bars of the entities each run of a comparison identified and those matched into it from other runs, side by side.'),
    ('identification_frequency', 'identification', 'Identification frequency', 'settings',
     'Grouped bars of the entities found in one, two ... all runs of a comparison, detected alone and detected or matched.'),
    ('shared_identifications', 'identification', 'Shared identifications', 'settings',
     'What every two runs of a comparison share (Jaccard index of the entities each detected), clustered so that runs alike sit together.'),
    ('identifications_across_runs', 'identification', 'Identifications across runs', 'settings',
     'Every entity any run of a comparison found, how many runs detected or found it and how each run found it. A click picks the entity.'),
    ('reporter_table', 'quantification', 'Reporter ions', 'settings',
     'The spectra of an isobarically labelled run with their retention time, precursor mass and how many labels carry a reporter ion, and, for an identified run, the protein each was identified as. A click picks the spectrum.'),
    ('reporter_ions', 'quantification', 'Reporter ion plot', 'settings',
     'The reporter ions of the selected spectrum, one per label, each label named at its m/z.'),
    ("filter_threshold", "quantification", "Filter threshold", "settings",
     "How many entries a filter keeps over its threshold, all entries for comparison and the current threshold marked."),
    ("volcano", "quantification", "Volcano plot", "show_volcano",
     "log2 fold change against the p-value of every entry of a group comparison, changes beyond "
     "both cut-offs coloured by direction, the most significant labelled."),
    ("pca", "quantification", "Sample similarity (PCA)", "pca_component",
     "Samples on their first principal components over the most variable entries, coloured by group."),
    ("clustered_heatmap", "quantification", "Clustered heatmap", "show_clustered_heatmap",
     "Row z-scores with entries and samples ordered by similarity, dendrograms and group colours."),
    ("zscore_heatmap", "quantification", "Z-score heatmap", "show_zscore_heatmap",
     "Row z-scores of the most variable entries in the input order, with a slider for how many."),
    ("abundance_profile", "quantification", "Abundance profile", "show_profile",
     "The picked entry's abundance per sample, samples side by side by group with a line at each "
     "group's mean; several picked entries as one series each."),
    ("comparison_table", "quantification", "Comparison table", "show_comparison_table",
     "Every entry of a group comparison, most significant first, with its change, log2 fold change "
     "and p-values."),
    ("missing_values", "quantification", "Where missing values occur", "show_missing_values",
     "Density of the mean abundance of complete entries and of entries with gaps."),
    ("imputed_values", "quantification", "Imputed values", "show_imputed_values",
     "The values imputation fills in against the measured ones."),
    ("normalization", "quantification", "Normalization", "show_normalization",
     "A box per sample of the abundances before and after normalization."),
    ("pvalue_histogram", "quantification", "p-value distribution", "show_pvalues",
     "Entries per p-value bin with the count expected when nothing changes."),
    ("go_enrichment", "quantification", "GO enrichment", "show_go_panel",
     "GO terms over-represented in the picked proteins, or how many proteins carry each term, as a "
     "chart and a table."),
    ("sample_counts", "quantification", "Counts per sample", "settings",
     "A bar per sample of a chosen count, such as identifications or quantified entries, coloured by condition."),
    ("total_intensity", "quantification", "Total intensity", "settings",
     "Bars of the summed intensity of every run or sample, coloured by condition, the median in the title."),
    ("replicate_cv", "quantification", "Variation between replicates", "settings",
     "A box per condition of the coefficients of variation of its entries; the picked entry is marked on every box."),
    ("match_quality", "quantification", "Match between runs", "settings",
     "A box per run of the match scores of the values matched into it, accepted and rejected matches apart."),
    ("feature_intensity", "quantification", "Feature intensity", "settings",
     "A box per run of the log2 intensity of the features it detected and of those matched into it; the picked feature is marked."),
    ("reporter_intensities", "quantification", "Reporter ion intensity", "settings",
     "A box per isobaric label of the log2 intensity of its reporter ions, coloured by condition, with the share of spectra carrying it."),
    ("reporter_ratios", "quantification", "Reporter ion ratios", "settings",
     "A box per isobaric label of the log2 ratio of its reporter ion to the reference label in the same spectrum."),
    ("labels_found", "quantification", "Labels found per spectrum", "settings",
     "Bars of the spectra carrying none, one ... all reporter ions of an isobaric labelling."),
    ("sample_correlation", "quantification", "Sample correlation", "settings",
     "The Pearson correlation of the log intensities of every two samples, clustered; replicates should correlate best."),
    ("entry_per_run", "quantification", "Picked entry per run", "settings",
     "The picked entry in every run with its abundance, condition, how its value was obtained and its match score."),
    ("feature_xic", "quantification", "Feature XIC", "settings",
     "The extracted ion chromatogram of the picked feature, the part inside its retention time bounds drawn apart."),
    ("condition_scatter", "quantification", "Condition scatter", "settings",
     "Every entry's mean abundance in one condition against another, with a line where both are equal and modified entries apart. A click picks the entry."),
    ("feature_map", "quantification", "Consensus feature map", "settings",
     "Every consensus feature by retention time and mass, coloured by the runs that detected it. A click picks the feature."),
    ("feature_table", "quantification", "Consensus feature table", "settings",
     "Every consensus feature with mass, retention time, charges and how many runs detected, matched or miss it. A click picks it."),
    ("feature_profile", "quantification", "Picked feature per run", "settings",
     "The picked consensus feature in every run, detected, matched or missing, with its intensity."),
]

COMPONENTS = [
    {"name": name, "folder": folder, "label": label, "module": f"src.viz.{folder}.{name}",
     "entry": entry, "description": description}
    for name, folder, label, entry, description in _ENTRIES
]


def components(folder: str | None = None) -> list[dict]:
    """The library's components, those of ``folder`` when given."""
    return [c for c in COMPONENTS if folder is None or c["folder"] == folder]


def component(name: str) -> dict:
    """The entry of ``name``; KeyError for a name the library lacks."""
    for entry in COMPONENTS:
        if entry["name"] == name:
            return entry
    raise KeyError(name)


def draw_function(name: str):
    """The function that draws ``name``."""
    import importlib

    entry = component(name)
    return getattr(importlib.import_module(entry["module"]), entry["entry"])
