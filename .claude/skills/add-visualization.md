# Add MS Data Visualization

Add mass spectrometry data visualizations using pyopenms-viz or OpenMS-Insight components.

MS data has specialized visualization needs: mass spectra (m/z vs intensity stick plots), chromatograms (RT vs intensity), 2D peak maps (RT vs m/z heatmaps), isotope patterns, fragment ion annotations, and statistical plots like volcano plots for differential expression.

## Instructions

1. **Ask the user** for:
   - What data to visualize (spectra, chromatograms, peak maps, tables, heatmaps)
   - Data size expectations (small/medium vs. large datasets with millions of points)
   - Whether interactive cross-component linking is needed

2. **Choose the right library**:

| Use Case | Library | Why |
|----------|---------|-----|
| Quick spectrum/chromatogram/peak map plots | **pyopenms-viz** | Simple one-liner API, publication quality |
| Large datasets (millions of points) | **OpenMS-Insight** | Server-side pagination, intelligent downsampling |
| Interactive tables with pagination | **OpenMS-Insight** `Table` | Tabulator.js, CSV export, server-side filtering |
| Cross-linked views (click table row → highlight in plot) | **OpenMS-Insight** | Shared `link_id` across components |
| Standard Plotly plots (bar, scatter, etc.) | **plotly.express** directly | Already available, use with `show_fig()` |

3. **Implement the visualization** in a page or workflow results section.

## pyopenms-viz Patterns

pyopenms-viz extends pandas DataFrames with MS-specific plot accessors. Always use the `plotly` backend for Streamlit.

```python
import pyopenms_viz
from src.common.common import show_fig

# Mass spectrum (stick plot from mz/intensity columns)
fig = df.plot.ms_spectrum(backend="plotly", title="MS1 Spectrum")
show_fig(fig, "spectrum-plot")

# 2D peak map (RT vs m/z, colored by intensity)
fig = df.plot.peak_map(backend="plotly")
show_fig(fig, "peak-map")

# Chromatogram (RT vs intensity)
fig = df.plot.chromatogram(backend="plotly")
show_fig(fig, "chromatogram")

# Mobilogram (ion mobility vs intensity)
fig = df.plot.mobilogram(backend="plotly")
show_fig(fig, "mobilogram")
```

**Key points:**
- DataFrame must have appropriate columns (e.g., `mz`, `intensity` for spectra)
- Always use `backend="plotly"` in Streamlit context
- Use `show_fig()` from `src/common/common.py` for consistent display with download buttons
- Import `pyopenms_viz` to register the plot accessors (even if not used directly)

## OpenMS-Insight Patterns

OpenMS-Insight provides Vue.js-backed interactive components optimized for large MS datasets.

```python
from openms_insight import Table, LinePlot, Heatmap, VolcanoPlot, SequenceView

# Interactive table with server-side pagination
Table(df, key="results-table", page_size=50)

# Stick-style mass spectrum
LinePlot(df, x="mz", y="intensity", key="spectrum-plot")

# 2D heatmap for large datasets (auto-downsampling)
Heatmap(df, x="rt", y="mz", z="intensity", key="peak-heatmap")

# Volcano plot for differential expression
VolcanoPlot(df, x="log2fc", y="neg_log10_pval", key="volcano")

# Peptide sequence with fragment ion annotations
SequenceView(sequence="PEPTIDER", ions=ion_df, key="sequence")
```

### Cross-Component Linking

Link components so selections in one update another:

```python
# Selecting a row in the table highlights the corresponding point in the plot
Table(df, key="linked-table", link_id="feature_id")
LinePlot(df, x="mz", y="intensity", key="linked-plot", link_id="feature_id")
Heatmap(df, x="rt", y="mz", z="intensity", key="linked-heatmap", link_id="feature_id")
```

All components sharing the same `link_id` column are automatically synchronized.

## Integration in Workflow Results

Add visualization to a workflow's `results()` method:

```python
@st.fragment
def results(self) -> None:
    result_file = Path(self.workflow_dir, "results", "step-name", "output.tsv")
    if result_file.exists():
        df = pd.read_csv(result_file, sep="\t")

        # pyopenms-viz for spectrum plots
        import pyopenms_viz
        fig = df.plot.ms_spectrum(backend="plotly")
        show_fig(fig, "results-spectrum")

        # Or OpenMS-Insight for interactive exploration
        from openms_insight import Table
        Table(df, key="results-table")
    else:
        st.warning("No results found. Please run the workflow first.")
```

## Reference Files

- Display utilities: `src/common/common.py` — `show_fig()`, `show_table()`
- Dependencies: `requirements.txt` — `pyopenms-viz`, `openms-insight`
- Example workflow results: `src/Workflow.py` — `results()` method

## Library Repositories

- **pyopenms-viz**: OpenMS/pyopenms-viz — pandas DataFrame `.plot()` extension with matplotlib/bokeh/plotly backends
- **OpenMS-Insight**: t0mdavid-m/openms-insight — Vue.js interactive Streamlit components with caching and downsampling

## Checklist

- [ ] Correct library chosen for the use case
- [ ] Dependencies present in `requirements.txt`
- [ ] `show_fig()` used for pyopenms-viz plots (consistent download/export behavior)
- [ ] `backend="plotly"` specified for all pyopenms-viz plots
- [ ] Unique `key=` values for all OpenMS-Insight components
- [ ] Cross-component linking set up if multiple views of same data
