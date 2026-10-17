import re
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from app.storage import R2Storage, StorageError

KEY_RE = re.compile(r"^outputs/\d{4}-\d{2}-\d{2}/[0-9a-f-]{36}\.json$")


@pytest.fixture
def client():
    return MagicMock()


@pytest.fixture
def storage(client):
    return R2Storage("acct", "id", "secret", "my-bucket", client=client)


def test_upload_key_and_content_type(storage, client):
    key = storage.upload(b"{}", "application/json", "json")
    assert KEY_RE.match(key)
    client.put_object.assert_called_once_with(
        Bucket="my-bucket", Key=key, Body=b"{}", ContentType="application/json"
    )


def test_keys_are_unique(storage):
    assert storage.upload(b"x", "text/plain", "txt") != storage.upload(b"x", "text/plain", "txt")


def test_presigned_url_uses_ttl(storage, client):
    client.generate_presigned_url.return_value = "https://signed"
    assert storage.presigned_url("outputs/k.json", 123) == "https://signed"
    client.generate_presigned_url.assert_called_once_with(
        "get_object", Params={"Bucket": "my-bucket", "Key": "outputs/k.json"}, ExpiresIn=123
    )


def test_upload_errors_wrapped(storage, client):
    client.put_object.side_effect = ClientError({"Error": {"Code": "500"}}, "PutObject")
    with pytest.raises(StorageError):
        storage.upload(b"x", "text/plain", "txt")
    client.put_object.side_effect = EndpointConnectionError(endpoint_url="https://x")
    with pytest.raises(StorageError):
        storage.upload(b"x", "text/plain", "txt")


def test_real_client_signs_without_network():
    s = R2Storage("acct", "id", "secret", "my-bucket")
    url = s.presigned_url("outputs/k.json", 600)
    assert url.startswith("https://acct.r2.cloudflarestorage.com/my-bucket/outputs/k.json?")
    assert "X-Amz-Expires=600" in url
