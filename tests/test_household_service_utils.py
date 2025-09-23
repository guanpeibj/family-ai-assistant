import uuid

from src.services.household_service import _normalize_user_id


def test_normalize_user_id_handles_uuid5_mapping():
    raw = "618"
    expected = str(uuid.uuid5(uuid.NAMESPACE_URL, f"faa:{raw}"))
    assert _normalize_user_id(raw) == expected


def test_normalize_user_id_passthrough_uuid():
    original = str(uuid.uuid4())
    assert _normalize_user_id(original) == original


def test_normalize_user_id_rejects_empty():
    assert _normalize_user_id("") is None
    assert _normalize_user_id(None) is None
