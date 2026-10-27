"""
The repository tree names every folder "Records / …"; a record filed under a
format's own root (storage_path "Line A / 2026 / …") must still be found when
that folder is chosen in the tree.
"""
from datetime import datetime

from app.models_qms import Record

from tests.test_qms_api import _login, client, world  # noqa: F401


def test_a_folder_chosen_in_the_tree_lists_records_filed_without_the_records_root(client, world):
    _login(client, world["names"]["po"])
    record = client.post("/api/records/call", json={"format_id": world["format_id"]}).json()

    db = client.db_factory()
    try:
        row = db.get(Record, record["id"])
        row.stage = "stored"
        row.storage_path = "Line A / 2026 / 10-Oct / 23"
        row.stored_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()

    _login(client, world["names"]["admin"])
    tree = client.get("/api/documents/repository").json()["folders"]
    assert any(node["path"] == "Records / Line A" for node in tree)

    for path in ("Records / Line A / 2026 / 10-Oct", "Line A / 2026", "Records / Line A / 2026 / 10-Oct / 23"):
        listed = client.get("/api/documents/repository", params={"folder_path": path}).json()
        assert [d["record_id"] for d in listed["documents"]] == [record["id"]], path

    # a sibling with a longer name is not swept in
    other = client.get("/api/documents/repository", params={"folder_path": "Records / Line"}).json()
    assert other["documents"] == []
