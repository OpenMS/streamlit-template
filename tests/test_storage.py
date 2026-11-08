"""src/common/storage.py: local paths by default, s3:// on the S3 tier."""

import datetime as dt

import pytest

from src.common import storage

S3_ENV = {
    "WORKSPACES_S3_ENDPOINT": "http://gw.example:9000/",
    "WORKSPACES_S3_BUCKET": "my-app",
    "WORKSPACES_S3_ACCESS_KEY": "AK",
    "WORKSPACES_S3_SECRET_KEY": "SK",
}


@pytest.fixture
def root(tmp_path, monkeypatch):
    for k in list(S3_ENV) + ["WORKSPACES_S3_REGION"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("WORKSPACES_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def s3(root, monkeypatch):
    for k, v in S3_ENV.items():
        monkeypatch.setenv(k, v)
    return root


def test_without_s3_everything_stays_local(root):
    p = root / "ws" / "results" / "a.parquet"
    assert not storage.s3_enabled()
    assert storage.uri(p) == str(p)
    assert storage.options() is None
    assert storage.presigned_url(p) is None


def test_partial_config_is_not_enabled(root, monkeypatch):
    monkeypatch.setenv("WORKSPACES_S3_ENDPOINT", "http://gw:9000")
    monkeypatch.setenv("WORKSPACES_S3_BUCKET", "my-app")
    assert not storage.s3_enabled()


def test_uri_maps_workspace_paths_to_the_app_bucket(s3):
    p = s3 / "ws id" / "results" / "a.parquet"
    assert storage.s3_enabled()
    assert storage.uri(p) == "s3://my-app/ws id/results/a.parquet"
    assert storage.uri(str(p)) == "s3://my-app/ws id/results/a.parquet"


def test_paths_outside_the_root_stay_local(s3, tmp_path_factory):
    other = tmp_path_factory.mktemp("elsewhere") / "x.parquet"
    assert storage.uri(other) == str(other)
    assert storage.uri(s3) == str(s3)
    assert storage.presigned_url(other) is None


def test_relative_dotdot_cannot_escape_the_root(s3):
    sneaky = s3 / "ws" / ".." / ".." / "etc" / "passwd"
    assert storage.uri(sneaky) == str(sneaky)


def test_polars_options(s3):
    opts = storage.options()
    assert opts["aws_endpoint_url"] == "http://gw.example:9000"
    assert opts["aws_access_key_id"] == "AK"
    assert opts["aws_secret_access_key"] == "SK"
    assert opts["aws_region"] == "us-east-1"
    assert opts["aws_allow_http"] == "true"


def test_presign_matches_the_aws_reference_vector():
    # "Example: Presigned URL" in the AWS S3 SigV4 query-string documentation.
    query = storage._presign_query(
        method="GET",
        host="examplebucket.s3.amazonaws.com",
        canonical_uri="/test.txt",
        access_key="AKIAIOSFODNN7EXAMPLE",
        secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        region="us-east-1",
        expires=86400,
        now=dt.datetime(2013, 5, 24, tzinfo=dt.timezone.utc),
    )
    assert query.endswith(
        "X-Amz-Signature=aeeed9bbccd4d02ee5c0109b86d86835f995330da4c265957d157751f604d404"
    )


def test_presigned_url_is_path_style_and_encoded(s3):
    url = storage.presigned_url(
        s3 / "ws id" / "a b.parquet",
        endpoint="https://files.example.org",
        now=dt.datetime(2026, 11, 3, tzinfo=dt.timezone.utc),
    )
    assert url.startswith("https://files.example.org/my-app/ws%20id/a%20b.parquet?")
    assert "X-Amz-Credential=AK%2F20261103%2Fus-east-1%2Fs3%2Faws4_request" in url
    assert "X-Amz-Signature=" in url
