from urllib.parse import parse_qs, urlparse

from app.storage import Storage, media_key


def test_media_key_is_scoped_by_shop_with_extension():
    key = media_key(12, "receipt", "image/png")
    assert key.startswith("shops/12/receipt/")
    assert key.endswith(".png")
    assert media_key(12, "receipt", "image/png") != key


def test_media_key_handles_codec_suffix_and_unknown_types():
    assert media_key(1, "audio", "audio/ogg; codecs=opus").endswith(".ogg")
    assert media_key(1, "misc", "application/x-unknown").endswith(".bin")


def test_presigned_url_points_to_r2_bucket(settings):
    settings.r2_account_id = "acc123"
    settings.r2_access_key_id = "AKIDTEST"
    settings.r2_secret_access_key = "secret"
    url = Storage(settings).presigned_url("shops/1/receipt/x.png", expires_in=600)

    parsed = urlparse(url)
    assert parsed.netloc == "acc123.r2.cloudflarestorage.com"
    assert parsed.path == "/kaye-media/shops/1/receipt/x.png"
    query = parse_qs(parsed.query)
    assert query["X-Amz-Expires"] == ["600"]
    assert query["X-Amz-Credential"][0].startswith("AKIDTEST/")
