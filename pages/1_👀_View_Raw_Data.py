from pathlib import Path
from streamlit_plotly_events import plotly_events

import streamlit as st

from src.common import page_setup, v_space, show_fig, save_params
from src import view
from src.captcha_ import captcha_control


params = page_setup()

# If run in hosted mode, show captcha as long as it has not been solved
if "controllo" not in st.session_state or params["controllo"] is False:
    # Apply captcha by calling the captcha_control function
    captcha_control()

st.title("View raw MS data")
selected_file = st.selectbox(
    "choose file",
    [f.name for f in Path(st.session_state.workspace, "mzML-files").iterdir()],
)
if selected_file:
    df = view.get_df(Path(st.session_state.workspace, "mzML-files", selected_file))
    df_MS1, df_MS2 = (
        df[df["mslevel"] == 1],
        df[df["mslevel"] == 2],
    )

    if not df_MS1.empty:
        tabs = st.tabs(
            ["📈 Base peak chromatogram and MS1 spectra", "📈 Peak map and MS2 spectra"]
        )
        with tabs[0]:
            # BPC and MS1 spec
            st.markdown("💡 Click a point in the BPC to show the MS1 spectrum.")
            bpc_fig = view.plot_bpc(df_MS1)

            # Determine RT positions from clicks in BPC to show MS1 at this position
            bpc_points = plotly_events(bpc_fig)
            if bpc_points:
                ms1_rt = bpc_points[0]["x"]
            else:
                ms1_rt = df_MS1.loc[0, "RT"]

            spec = df_MS1.loc[df_MS1["RT"] == ms1_rt].squeeze()

            title = f"MS1 spectrum @RT {spec['RT']}"
            fig = view.plot_ms_spectrum(
                spec,
                title,
                "#EF553B",
            )
            show_fig(fig, title.replace(" ", "_"))

        with tabs[1]:
            c1, c2 = st.columns(2)
            c1.number_input(
                "2D map intensity cutoff",
                1000,
                1000000000,
                params["2D-map-intensity-cutoff"],
                1000,
                key="2D-map-intensity-cutoff",
            )
            v_space(1, c2)
            c2.markdown("💡 Click anywhere to show the closest MS2 spectrum.")
            map2D = view.plot_2D_map(
                df_MS1,
                df_MS2,
                st.session_state["2D-map-intensity-cutoff"],
            )
            map_points = plotly_events(map2D)
            # Determine RT and mz positions from clicks in the map to get closest MS2 spectrum
            if not df_MS2.empty:
                if map_points:
                    rt = map_points[0]["x"]
                    prec_mz = map_points[0]["y"]
                else:
                    rt = df_MS2.iloc[0, 2]
                    prec_mz = df_MS2.iloc[0, 0]
                spec = df_MS2.loc[
                    (
                        abs(df_MS2["RT"] - rt) + abs(df_MS2["precursormz"] - prec_mz)
                    ).idxmin(),
                    :,
                ]
                title = f"MS2 spectrum @precursor m/z {round(spec['precursormz'], 4)} @RT {round(spec['RT'], 2)}"

                ms2_fig = view.plot_ms_spectrum(spec, title, "#00CC96")
                show_fig(ms2_fig, title.replace(" ", "_"))

save_params(params)
