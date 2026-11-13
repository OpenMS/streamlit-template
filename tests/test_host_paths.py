"""Host folder links retain the host OS syntax when served from Linux/Docker."""

import pytest

from src.workflow.host_paths import folder_file_uri, folder_reference


@pytest.mark.parametrize("folder,uri", [
    ("/home/samuel/MS data", "file:///home/samuel/MS%20data/"),
    ("/Users/Sam/MS data/#batch 1", "file:///Users/Sam/MS%20data/%23batch%201/"),
    (r"C:\Users\Sam\MS data", "file:///C:/Users/Sam/MS%20data/"),
    ("D:/RNA data/batch 1/", "file:///D:/RNA%20data/batch%201/"),
    (r"\\nas\MS data\batch#1", "file://nas/MS%20data/batch%231/"),
    ("//nas/MS data/batch#1", "file://nas/MS%20data/batch%231/"),
    ("/data/München/100%", "file:///data/M%C3%BCnchen/100%25/"),
    ("/data/[RNA](test)?", "file:///data/%5BRNA%5D%28test%29%3F/"),
    ("/", "file:///"),
    ("C:/", "file:///C:/"),
])
def test_absolute_host_folder_uri_is_lexical_and_encoded(folder, uri):
    assert folder_file_uri(folder) == uri
    assert folder_reference(folder).endswith(f"](<{uri}>)")
    assert folder in folder_reference(folder)


@pytest.mark.parametrize("folder", [
    "./data", "data", "../MS data", "~/data", "C:data", r"\data", "",
    "https://example.com/data", "javascript:alert(1)", "/data/line\nbreak",
    "\\\\?\\C:\\data", "\\\\.\\C:\\data",
])
def test_relative_or_non_file_paths_are_not_resolved_against_the_server(folder):
    assert folder_file_uri(folder) is None
    reference = folder_reference(folder)
    assert "file:" not in reference
    assert not reference.startswith("[")


def test_markdown_looking_names_are_literal_and_backticks_cannot_close_the_label():
    folder = "/data/`RNA``/[click](https://example.com)/&amp;"
    reference = folder_reference(folder)
    assert reference.startswith("[``` " + folder + " ```]")
    assert reference.endswith("file:///data/%60RNA%60%60/%5Bclick%5D%28https%3A/example.com%29/%26amp%3B/>)")
