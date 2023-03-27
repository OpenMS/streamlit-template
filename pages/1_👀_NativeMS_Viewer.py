import streamlit as st
from src.view import *
from src.common import *
from streamlit_plotly_events import plotly_events


def content():
    page_setup()
    sidebar()
    st.title("NativeMS Viewer")

    # st.session_state.view_spectra_dict = get_spectra_dict(
    #     st.session_state["mzML-files"]
    # )
    st.selectbox(
        "choose file",
        [f.name for f in st.session_state["deconv-mzML-files"].iterdir()],
        key="selected_file",
    )

    # deconv_mzml =
    spectra_container, mass_container = st.columns(2)

    #
    # df = get_df(st.session_state.view_file)
    # df_MS1, df_MS2 = (
    #     df[df["mslevel"] == 1],
    #     df[df["mslevel"] == 2],
    # )

    # if not df_MS1.empty:
    #     st.markdown("### Peak Map and MS2 spectra")
    #     c1, c2 = st.columns(2)
    #     c1.number_input(
    #         "2D map intensity cutoff",
    #         1000,
    #         1000000000,
    #         5000,
    #         1000,
    #         key="cutoff",
    #     )
    #     if not df_MS2.empty:
    #         c2.markdown("##")
    #         c2.markdown("💡 Click anywhere to show the closest MS2 spectrum.")
    #     st.session_state.view_fig_map = plot_2D_map(
    #         df_MS1,
    #         df_MS2,
    #         st.session_state.cutoff,
    #     )
    #     # Determine RT and mz positions from clicks in the map to get closest MS2 spectrum
    #     if not df_MS2.empty:
    #         map_points = plotly_events(st.session_state.view_fig_map)
    #         if map_points:
    #             rt = map_points[0]["x"]
    #             prec_mz = map_points[0]["y"]
    #         else:
    #             rt = df_MS2.iloc[0, 2]
    #             prec_mz = df_MS2.iloc[0, 0]
    #         spec = df_MS2.loc[
    #             (
    #                 abs(df_MS2["RT"] - rt) + abs(df_MS2["precursormz"] - prec_mz)
    #             ).idxmin(),
    #             :,
    #         ]
    #         plot_ms_spectrum(
    #             spec,
    #             f"MS2 spectrum @precursor m/z {round(spec['precursormz'], 4)} @RT {round(spec['RT'], 2)}",
    #             "#00CC96",
    #         )
    #     else:
    #         st.plotly_chart(st.session_state.view_fig_map, use_container_width=True)
    #
    #     # BPC and MS1 spec
    #     st.markdown("### Base Peak Chromatogram (BPC)")
    #     st.markdown("💡 Click a point in the BPC to show the MS1 spectrum.")
    #     st.session_state.view_fig_bpc = plot_bpc(df_MS1)
    #
    #     # Determine RT positions from clicks in BPC to show MS1 at this position
    #     bpc_points = plotly_events(st.session_state.view_fig_bpc)
    #     if bpc_points:
    #         st.session_state.view_MS1_RT = bpc_points[0]["x"]
    #     else:
    #         st.session_state.view_MS1_RT = df_MS1.loc[0, "RT"]
    #
    #     spec = df_MS1.loc[df_MS1["RT"] == st.session_state.view_MS1_RT].squeeze()
    #
    #     plot_ms_spectrum(
    #         spec,
    #         f"MS1 spectrum @RT {spec['RT']}",
    #         "#EF553B",
    #     )


if __name__ == "__main__":
    # try:
    content()
    # except:
    #     st.warning(ERRORS["visualization"])
