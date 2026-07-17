"""
Tests for cloud storage providers using sys.modules mocking.
SDKs (boto3, google-cloud-storage, azure-storage-blob) are imported
lazily inside __init__, so we inject fakes via sys.modules.
"""
from __future__ import annotations

import json
import sys
from types import ModuleType
from unittest.mock import MagicMock


# ─── helpers ─────────────────────────────────────────────────────────────────

def _make_s3_store(mock_client):
    """Inject a fake boto3 and return an S3Storage wired to mock_client."""
    fake_boto3 = ModuleType("boto3")
    fake_botocore = ModuleType("botocore")
    fake_botocore_config = ModuleType("botocore.config")
    fake_botocore_config.Config = MagicMock(return_value=MagicMock())
    fake_boto3.client = MagicMock(return_value=mock_client)
    mock_client.head_bucket.return_value = {}

    sys.modules.setdefault("boto3", fake_boto3)
    sys.modules.setdefault("botocore", fake_botocore)
    sys.modules.setdefault("botocore.config", fake_botocore_config)

    if "storage.s3_storage" in sys.modules:
        del sys.modules["storage.s3_storage"]

    from storage.s3_storage import S3Storage
    store = S3Storage(bucket="test-bucket", region="us-east-1")
    store._client = mock_client
    return store


def _make_gcs_store(mock_client, mock_bucket):
    fake_google = ModuleType("google")
    fake_google_cloud = ModuleType("google.cloud")
    fake_storage_mod = ModuleType("google.cloud.storage")
    fake_storage_mod.Client = MagicMock(return_value=mock_client)
    mock_client.bucket.return_value = mock_bucket

    sys.modules["google"] = fake_google
    sys.modules["google.cloud"] = fake_google_cloud
    sys.modules["google.cloud.storage"] = fake_storage_mod

    if "storage.gcs_storage" in sys.modules:
        del sys.modules["storage.gcs_storage"]

    from storage.gcs_storage import GCSStorage
    store = GCSStorage(bucket="test-bucket")
    store._client = mock_client
    store._bucket = mock_bucket
    return store


def _make_azure_store(mock_service, mock_container):
    fake_azure = ModuleType("azure")
    fake_azure_storage = ModuleType("azure.storage")
    fake_azure_blob = ModuleType("azure.storage.blob")
    mock_svc_cls = MagicMock(return_value=mock_service)
    fake_azure_blob.BlobServiceClient = mock_svc_cls
    mock_svc_cls.from_connection_string = MagicMock(return_value=mock_service)
    mock_service.get_container_client.return_value = mock_container
    mock_container.exists.return_value = True

    sys.modules["azure"] = fake_azure
    sys.modules["azure.storage"] = fake_azure_storage
    sys.modules["azure.storage.blob"] = fake_azure_blob

    if "storage.azure_storage" in sys.modules:
        del sys.modules["storage.azure_storage"]

    from storage.azure_storage import AzureBlobStorage
    store = AzureBlobStorage(
        container="test-container",
        connection_string="DefaultEndpointsProtocol=https;AccountName=x;AccountKey=y;EndpointSuffix=core.windows.net",
    )
    store._container_client = mock_container
    return store


# ─── S3Storage ───────────────────────────────────────────────────────────────

class TestS3Storage:

    def test_put_json_calls_put_object(self):
        mock_client = MagicMock()
        store = _make_s3_store(mock_client)
        store.put_json("test/key.json", {"foo": "bar"})
        mock_client.put_object.assert_called_once()
        kw = mock_client.put_object.call_args[1]
        assert kw["Bucket"] == "test-bucket"
        assert kw["Key"] == "test/key.json"
        assert kw["ContentType"] == "application/json"
        assert json.loads(kw["Body"].decode()) == {"foo": "bar"}

    def test_get_json_returns_parsed_data(self):
        mock_client = MagicMock()
        store = _make_s3_store(mock_client)
        body = MagicMock()
        body.read.return_value = json.dumps({"result": 42}).encode()
        mock_client.get_object.return_value = {"Body": body}
        assert store.get_json("test/key.json") == {"result": 42}

    def test_get_json_returns_none_when_missing(self):
        mock_client = MagicMock()
        store = _make_s3_store(mock_client)
        # S3Storage catches self._client.exceptions.NoSuchKey — make it a real exception class
        class NoSuchKey(Exception):
            pass
        mock_client.exceptions.NoSuchKey = NoSuchKey
        mock_client.get_object.side_effect = NoSuchKey("key not found")
        assert store.get_json("missing.json") is None

    def test_list_keys_returns_sorted(self):
        mock_client = MagicMock()
        store = _make_s3_store(mock_client)
        paginator = MagicMock()
        mock_client.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {"Contents": [{"Key": "b.json"}, {"Key": "a.json"}]}
        ]
        assert store.list_keys("prefix/") == ["a.json", "b.json"]

    def test_delete_returns_true_when_exists(self):
        mock_client = MagicMock()
        store = _make_s3_store(mock_client)
        mock_client.head_object.return_value = {}
        assert store.delete("test/key.json") is True
        mock_client.delete_object.assert_called_once_with(
            Bucket="test-bucket", Key="test/key.json"
        )

    def test_delete_returns_false_when_missing(self):
        mock_client = MagicMock()
        store = _make_s3_store(mock_client)
        mock_client.head_object.side_effect = Exception("404")
        assert store.delete("missing.json") is False


# ─── GCSStorage ──────────────────────────────────────────────────────────────

class TestGCSStorage:

    def test_put_json_uploads_blob(self):
        mock_client, mock_bucket = MagicMock(), MagicMock()
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        store = _make_gcs_store(mock_client, mock_bucket)
        store.put_json("test/key.json", {"hello": "world"})
        mock_blob.upload_from_string.assert_called_once()
        args, kwargs = mock_blob.upload_from_string.call_args
        assert json.loads(args[0].decode()) == {"hello": "world"}
        assert kwargs.get("content_type") == "application/json"

    def test_get_json_returns_parsed_data(self):
        mock_client, mock_bucket = MagicMock(), MagicMock()
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_blob.exists.return_value = True
        mock_blob.download_as_bytes.return_value = json.dumps({"val": 1}).encode()
        store = _make_gcs_store(mock_client, mock_bucket)
        assert store.get_json("test/key.json") == {"val": 1}

    def test_get_json_returns_none_when_missing(self):
        mock_client, mock_bucket = MagicMock(), MagicMock()
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_blob.exists.return_value = False
        store = _make_gcs_store(mock_client, mock_bucket)
        assert store.get_json("missing.json") is None

    def test_list_keys_returns_sorted(self):
        mock_client, mock_bucket = MagicMock(), MagicMock()
        b1, b2 = MagicMock(), MagicMock()
        b1.name, b2.name = "z.json", "a.json"
        mock_client.list_blobs.return_value = [b1, b2]
        store = _make_gcs_store(mock_client, mock_bucket)
        assert store.list_keys("prefix/") == ["a.json", "z.json"]

    def test_delete_returns_true_when_exists(self):
        mock_client, mock_bucket = MagicMock(), MagicMock()
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_blob.exists.return_value = True
        store = _make_gcs_store(mock_client, mock_bucket)
        assert store.delete("test/key.json") is True
        mock_blob.delete.assert_called_once()


# ─── AzureBlobStorage ────────────────────────────────────────────────────────

class TestAzureBlobStorage:

    def test_put_json_uploads_blob(self):
        mock_svc, mock_container = MagicMock(), MagicMock()
        mock_blob = MagicMock()
        mock_container.get_blob_client.return_value = mock_blob
        store = _make_azure_store(mock_svc, mock_container)
        store.put_json("test/key.json", {"azure": True})
        mock_blob.upload_blob.assert_called_once()
        args, _ = mock_blob.upload_blob.call_args
        assert json.loads(args[0].decode()) == {"azure": True}

    def test_get_json_returns_parsed_data(self):
        mock_svc, mock_container = MagicMock(), MagicMock()
        mock_blob = MagicMock()
        mock_container.get_blob_client.return_value = mock_blob
        mock_blob.exists.return_value = True
        dl = MagicMock()
        dl.readall.return_value = json.dumps({"az": 99}).encode()
        mock_blob.download_blob.return_value = dl
        store = _make_azure_store(mock_svc, mock_container)
        assert store.get_json("test/key.json") == {"az": 99}

    def test_get_json_returns_none_when_missing(self):
        mock_svc, mock_container = MagicMock(), MagicMock()
        mock_blob = MagicMock()
        mock_container.get_blob_client.return_value = mock_blob
        mock_blob.exists.return_value = False
        store = _make_azure_store(mock_svc, mock_container)
        assert store.get_json("missing.json") is None

    def test_delete_returns_false_when_missing(self):
        mock_svc, mock_container = MagicMock(), MagicMock()
        mock_blob = MagicMock()
        mock_container.get_blob_client.return_value = mock_blob
        mock_blob.exists.return_value = False
        store = _make_azure_store(mock_svc, mock_container)
        assert store.delete("missing.json") is False
