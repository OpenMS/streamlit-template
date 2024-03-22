from PyInstaller.utils.hooks import collect_data_files, copy_metadata

datas = []
datas += [("myenv/Lib/site-packages/streamlit/runtime", "./streamlit/runtime")]
datas += collect_data_files("streamlit")
datas += copy_metadata("streamlit")
datas += copy_metadata("streamlit_plotly_events")
datas += collect_data_files("st_pages")
datas += copy_metadata("st_pages")
datas += copy_metadata("pyopenms")
datas += copy_metadata("captcha")
datas += copy_metadata("pyarrow")
