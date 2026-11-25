"""Acquisition decisions: the masses of every survey scan by retention time and
mass, with the precursors an intelligent acquisition chose (and those it
identified) drawn over them. A click picks the precursor.

Insight component: ``Heatmap``. Columns: ``rt``, ``mass``, ``intensity``,
``precursor`` (empty for a survey mass that was not chosen), ``label`` (hover
text), and either ``Decision`` (``Deconvolved``, ``Chosen``, ``Identified``)
or, with an openms-insight whose Heatmap takes ``color_columns``, ``Layer``
plus the value columns in ``COLOR_COLUMNS``.
"""

from __future__ import annotations

COMPONENT = "Heatmap"

COLORS = {'Deconvolved': '#9aa5b1', 'Chosen': '#f08c00', 'Identified': '#2b8a3e'}

# What the map can be coloured by besides the intensity (toolbar "Color")
COLOR_COLUMNS = {
    'QScore': 'qscore',
    '# deconvolved MS2 masses': 'ms2_masses',
    '# fragment ions': 'fragment_ions',
}


def settings(selection: str = "precursor", zoom: str | None = None,
             filename: str = "acquisition-decisions", by_value: bool = False,
             **overrides) -> dict:
    """Constructor arguments; ``by_value`` colours by a value of
    ``COLOR_COLUMNS`` with layers instead of by decision. The render-time
    options are ``render(by_value)``."""
    arguments = dict(
        x_column='rt', y_column='mass', intensity_column='intensity',
        interactivity={selection: 'precursor'}, highlight={selection: 'precursor'},
        hover_column='label', title='Survey masses and chosen precursors',
        x_label='Retention time (min)', y_label='Monoisotopic mass (Da)',
        min_points=50000, downsample_zoomed=False, svg_filename=filename,
        scroll_zoom=False,
    )
    if zoom:
        arguments['zoom_identifier'] = zoom
    if not by_value:
        arguments['category_column'] = 'Decision'
    return arguments | overrides


def render(by_value: bool = False) -> dict:
    """Styling passed at render time, not stored with the cache."""
    if by_value:
        return dict(color_columns=COLOR_COLUMNS, layer_column='Layer')
    return dict(category_colors=COLORS)
