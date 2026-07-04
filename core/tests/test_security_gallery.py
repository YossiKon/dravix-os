"""Security gallery API: list by day, timestamps, delete (one/day/all), zip download."""
from __future__ import annotations

import io
import zipfile

from fastapi.testclient import TestClient


def _app(monkeypatch, tmp_path):
    monkeypatch.setenv("DRAVIX_ROBOT_DRIVER", "mock")
    monkeypatch.setenv("DRAVIX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DRAVIX_HA_URL", "")
    monkeypatch.setenv("DRAVIX_HA_TOKEN", "")
    monkeypatch.setenv("DRAVIX_XIAOZHI_MCP_URL", "")
    monkeypatch.setenv("DRAVIX_API_TOKEN", "")
    from dravix.config import get_settings

    get_settings.cache_clear()
    from dravix.app import create_app

    return create_app()


def _seed(tmp_path):
    a = tmp_path / "security" / "2026-07-04"
    a.mkdir(parents=True)
    (a / "153012.jpg").write_bytes(b"\xff\xd8jpeg-one")
    (a / "153020.jpg").write_bytes(b"\xff\xd8jpeg-two")
    b = tmp_path / "security" / "2026-07-03"
    b.mkdir(parents=True)
    (b / "090000.jpg").write_bytes(b"\xff\xd8x")


def test_days_photos_and_download(tmp_path, monkeypatch):
    _seed(tmp_path)
    app = _app(monkeypatch, tmp_path)
    try:
        with TestClient(app) as c:
            days = c.get("/api/security/days").json()["days"]
            assert [d["day"] for d in days] == ["2026-07-04", "2026-07-03"]  # newest first
            assert days[0]["count"] == 2 and days[0]["has_video"] is False

            p = c.get("/api/security/photos?day=2026-07-04&limit=100").json()
            assert p["total"] == 2
            assert p["photos"][0]["ts"] == "2026-07-04T15:30:20"  # newest first, ISO ts

            img = c.get("/api/security/photo/2026-07-04/153012.jpg")
            assert img.status_code == 200 and img.content.startswith(b"\xff\xd8")
            dl = c.get("/api/security/photo/2026-07-04/153012.jpg?download=1")
            assert "attachment" in dl.headers.get("content-disposition", "")
    finally:
        from dravix.config import get_settings

        get_settings.cache_clear()


def test_delete_photo_prunes_empty_day(tmp_path, monkeypatch):
    _seed(tmp_path)
    app = _app(monkeypatch, tmp_path)
    try:
        with TestClient(app) as c:
            assert c.delete("/api/security/photo/2026-07-03/090000.jpg").status_code == 200
            days = [d["day"] for d in c.get("/api/security/days").json()["days"]]
            assert "2026-07-03" not in days  # its only photo is gone → folder pruned
            assert "2026-07-04" in days
    finally:
        from dravix.config import get_settings

        get_settings.cache_clear()


def test_delete_day_and_clear_all(tmp_path, monkeypatch):
    _seed(tmp_path)
    app = _app(monkeypatch, tmp_path)
    try:
        with TestClient(app) as c:
            assert c.delete("/api/security/day/2026-07-04").json()["deleted"] == 2
            c.delete("/api/security/photos")
            assert c.get("/api/security/days").json()["days"] == []
    finally:
        from dravix.config import get_settings

        get_settings.cache_clear()


def test_zip_a_day(tmp_path, monkeypatch):
    _seed(tmp_path)
    app = _app(monkeypatch, tmp_path)
    try:
        with TestClient(app) as c:
            z = c.get("/api/security/day/2026-07-04/zip")
            assert z.status_code == 200 and z.headers["content-type"] == "application/zip"
            names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
            assert "2026-07-04/153012.jpg" in names and "2026-07-04/153020.jpg" in names
    finally:
        from dravix.config import get_settings

        get_settings.cache_clear()


def test_bad_paths_rejected(tmp_path, monkeypatch):
    app = _app(monkeypatch, tmp_path)
    try:
        with TestClient(app) as c:
            assert c.get("/api/security/photo/nope/153012.jpg").status_code == 400
            assert c.get("/api/security/photo/2026-07-04/evil.txt").status_code == 400
            assert c.delete("/api/security/day/notaday").status_code == 400  # regex-guarded
    finally:
        from dravix.config import get_settings

        get_settings.cache_clear()
