from PyInstaller.utils.hooks import copy_metadata

datas = []
datas += copy_metadata("streamlit")
datas += copy_metadata("pyopenms")
datas += copy_metadata("captcha")
datas += copy_metadata("pyarrow")
