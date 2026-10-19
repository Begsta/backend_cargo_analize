"""Проверки HTTP API с настоящими ORM-запросами к SQLite и подменённым MinIO."""

import json
import os
import unittest
from datetime import UTC, datetime
from unittest.mock import patch
from urllib.parse import urlsplit

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

for name, value in {
    "DB_HOST": "localhost", "DB_PORT": "5433", "DB_USER": "cargo",
    "DB_PASSWORD": "cargo", "DB_NAME": "cargo_db",
}.items():
    os.environ.setdefault(name, value)

from db.base import Base  # noqa: E402
from db.session import get_db  # noqa: E402
from main import app  # noqa: E402
from models.cargo import Cargo  # noqa: E402
from models.like import Like  # noqa: E402
from models.user import User  # noqa: E402


class AsyncDatabase:
    def __init__(self, session):
        self.session = session

    async def execute(self, stmt):
        return self.session.execute(stmt)

    async def get(self, model, key):
        return self.session.get(model, key)

    def add(self, item):
        self.session.add(item)

    async def commit(self):
        self.session.commit()

    async def refresh(self, item):
        self.session.refresh(item)

    async def rollback(self):
        self.session.rollback()

    async def delete(self, item):
        self.session.delete(item)


async def request(method, url, *, body=None, fields=None, files=None):
    headers = []
    raw = b""
    if body is not None:
        raw = json.dumps(body).encode()
        headers.append((b"content-type", b"application/json"))
    if fields is not None or files is not None:
        boundary = "lab3-test-boundary"
        parts = []
        for name, value in (fields or {}).items():
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'
                f'\r\n\r\n{value}\r\n'.encode(),
            )
        for name, (filename, content, media_type) in (files or {}).items():
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
                f'filename="{filename}"\r\nContent-Type: {media_type}\r\n\r\n'.encode()
                + content + b"\r\n",
            )
        raw = b"".join(parts) + f"--{boundary}--\r\n".encode()
        headers.append((b"content-type", f"multipart/form-data; boundary={boundary}".encode()))
    headers.append((b"content-length", str(len(raw)).encode()))
    parsed = urlsplit(url)
    scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1", "method": method, "scheme": "http",
        "path": parsed.path, "raw_path": parsed.path.encode(),
        "query_string": parsed.query.encode(), "headers": headers,
        "client": ("127.0.0.1", 1234), "server": ("testserver", 80),
        "root_path": "",
    }
    messages = []

    async def receive():
        return {"type": "http.request", "body": raw, "more_body": False}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    content = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return status, json.loads(content) if content else None


class Lab3Tests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine, expire_on_commit=False)
        self.session.add_all([
            User(user_id=1, user_login="creator", user_name="Создатель"),
            User(user_id=2, user_login="other", user_name="Другой"),
        ])
        self.session.commit()
        self.database = AsyncDatabase(self.session)

        async def database_override():
            yield self.database

        app.dependency_overrides[get_db] = database_override
        self.uploads = []

        async def inline_storage_call(function, *args, **kwargs):
            # MinIO подменён: реальные потоки и внешние соединения не нужны.
            return function(*args, **kwargs)

        self.patches = [
            patch("api.cargos.ensure_bucket"),
            patch("api.cargos.upload_bytes", side_effect=lambda *args: self.uploads.append(args)),
            patch("api.cargos.asyncio.to_thread", new=inline_storage_call),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        app.dependency_overrides.clear()
        self.session.close()
        self.engine.dispose()

    def cargo(self, cargo_id=1, status="published", creator=1, mass=None):
        now = datetime.now(UTC).replace(tzinfo=None)
        item = Cargo(
            cargo_id=cargo_id, cargo_name=f"Груз {cargo_id}", cargo_description=None,
            publication_status=status, image_url="image.png", video_url="video.mp4",
            cargo_mass=mass, cargo_volume=None, created_at=now, formed_at=now,
            creator_user_id=creator,
        )
        self.session.add(item)
        self.session.commit()
        return item

    async def create(self, fields=None, files=None, url="/api/cargos"):
        return await request(
            "POST", url, fields={"cargo_name": "Панель"} if fields is None else fields,
            files={
                "image": ("photo.png", b"image content", "image/png"),
                "video": ("clip.mp4", b"video content", "video/mp4"),
            } if files is None else files,
        )

    async def test_create_only_three_fields(self):
        status, data = await self.create()
        self.assertEqual(status, 201)
        self.assertEqual(data["publication_status"], "draft")
        self.assertEqual(data["creator_user_id"], 1)
        for name in ("cargo_description", "cargo_mass", "cargo_volume"):
            self.assertIsNone(data[name])
        self.assertEqual(len(self.uploads), 2)
        for name in ("image_url", "video_url"):
            self.assertTrue(data[name].isascii())
            self.assertNotIn("/", data[name])

    async def test_missing_required_fields(self):
        for missing in ("cargo_name", "image", "video"):
            with self.subTest(missing=missing):
                files = {
                    "image": ("photo.png", b"image", "image/png"),
                    "video": ("clip.mp4", b"video", "video/mp4"),
                }
                fields = {"cargo_name": "Панель"}
                files.pop(missing, None)
                fields.pop(missing, None)
                status, _ = await self.create(fields=fields, files=files)
                self.assertEqual(status, 422)
        self.assertEqual(self.uploads, [])

    async def test_blank_name_and_extra_fields_rejected(self):
        for fields in (
            {"cargo_name": "   "}, {"cargo_name": "x" * 257},
            {"cargo_name": "Груз", "creator_user_id": "2"},
            {"cargo_name": "Груз", "cargo_mass": "4"},
        ):
            with self.subTest(fields=fields):
                status, _ = await self.create(fields=fields)
                self.assertEqual(status, 422)
        self.assertEqual(self.uploads, [])

    async def test_empty_file_rejected(self):
        status, _ = await self.create(files={
            "image": ("photo.png", b"", "image/png"),
            "video": ("clip.mp4", b"video", "video/mp4"),
        })
        self.assertEqual(status, 422)
        self.assertEqual(self.uploads, [])

    async def test_second_draft_rejected(self):
        self.cargo(status="draft")
        status, _ = await self.create()
        self.assertEqual(status, 409)
        self.assertEqual(self.uploads, [])

    async def test_publish_with_optional_fields(self):
        self.cargo(status="draft")
        status, data = await request("PUT", "/api/cargos/1", body={
            "cargo_description": "Описание", "cargo_mass": 5.5, "cargo_volume": 0,
        })
        self.assertEqual(status, 200)
        self.assertEqual(data["publication_status"], "published")
        self.assertEqual(data["cargo_mass"], 5.5)
        self.assertEqual(data["cargo_volume"], 0)
        self.assertEqual(data["cargo_description"], "Описание")

    async def test_publish_without_body(self):
        self.cargo(status="draft")
        status, data = await request("PUT", "/api/cargos/1")
        self.assertEqual(status, 200)
        self.assertIsNone(data["cargo_mass"])
        self.assertIsNone(data["cargo_description"])

    async def test_publish_validation(self):
        self.cargo(status="draft")
        for body in (
            {"publication_status": "published"}, {"creator_user_id": 2},
            {"cargo_mass": -1}, {"cargo_volume": "nan"}, {"cargo_mass": "inf"},
        ):
            with self.subTest(body=body):
                status, _ = await request("PUT", "/api/cargos/1", body=body)
                self.assertEqual(status, 422)
        self.assertEqual(self.session.get(Cargo, 1).publication_status, "draft")

    async def test_publish_foreign_and_published_rejected(self):
        self.cargo(1, "draft", creator=2)
        self.cargo(2)
        status, _ = await request("PUT", "/api/cargos/1", body={"cargo_mass": 7})
        self.assertEqual(status, 403)
        status, _ = await request("PUT", "/api/cargos/2")
        self.assertEqual(status, 409)

    async def test_list_filters_and_creator(self):
        self.cargo(1, mass=4)
        self.cargo(2, creator=2, mass=7)
        self.cargo(3, "draft", mass=9)
        self.cargo(4, "deleted", mass=10)
        self.cargo(5)
        status, data = await request("GET", "/api/cargos?cargo_mass=4")
        self.assertEqual(status, 200)
        self.assertEqual([x["cargo_id"] for x in data], [1, 2])
        self.assertEqual([x["is_creator"] for x in data], [1, 0])
        _, data = await request("GET", "/api/cargos?cargo_mass=0")
        self.assertEqual([x["cargo_id"] for x in data], [1, 2, 5])

    async def test_feed_order_wrap_and_visibility(self):
        self.cargo(9)
        self.cargo(2)
        self.cargo(4, "draft")
        self.cargo(6, "deleted")
        for query, expected in (
            ("", 2), ("?cargo_id=2", 2), ("?cargo_id=2&next=true", 9),
            ("?cargo_id=9&next=true", 2), ("?cargo_id=5&next=true", 9),
        ):
            with self.subTest(query=query):
                status, data = await request("GET", "/api/cargos/feed" + query)
                self.assertEqual(status, 200)
                self.assertEqual(data["cargo_id"], expected)
        for query, expected in (("?cargo_id=4", 404), ("?next=true", 422)):
            status, _ = await request("GET", "/api/cargos/feed" + query)
            self.assertEqual(status, expected)

    async def test_empty_feed(self):
        status, _ = await request("GET", "/api/cargos/feed")
        self.assertEqual(status, 404)

    async def test_personal_like_independent_of_creator_and_count(self):
        self.cargo(1, creator=2)
        self.session.add(Like(cargo_id=1, user_id=2))
        self.session.commit()
        _, data = await request("GET", "/api/cargos/feed?cargo_id=1")
        self.assertEqual((data["is_creator"], data["is_liked"], data["interest_marks"]), (0, 0, 1))
        for value, expected_count in ((1, 2), (1, 2), (0, 1), (0, 1)):
            status, _ = await request("POST", "/api/cargos/1/likes", body={"interest": value})
            self.assertEqual(status, 200)
            status, data = await request("GET", "/api/cargos/feed?cargo_id=1")
            self.assertEqual(status, 200)
            self.assertEqual(data["is_liked"], value)
            self.assertEqual(data["interest_marks"], expected_count)

    async def test_own_cargo_without_like(self):
        self.cargo()
        _, data = await request("GET", "/api/cargos/feed")
        self.assertEqual((data["is_creator"], data["is_liked"]), (1, 0))

    async def test_soft_delete_and_foreign_owner(self):
        self.cargo(1)
        self.cargo(2, creator=2)
        status, _ = await request("DELETE", "/api/cargos/2")
        self.assertEqual(status, 403)
        status, data = await request("DELETE", "/api/cargos/1")
        self.assertEqual((status, data), (204, None))
        self.assertEqual(self.session.get(Cargo, 1).publication_status, "deleted")
        _, data = await request("GET", "/api/cargos")
        self.assertEqual([x["cargo_id"] for x in data], [2])

    async def test_draft_without_id(self):
        self.cargo(1, "draft", creator=2)
        self.cargo(2, "draft")
        status, data = await request("GET", "/api/cargos/draft")
        self.assertEqual(status, 200)
        self.assertEqual(data["cargo_id"], 2)

    async def test_html_next_requires_and_uploads_media(self):
        status, _ = await self.create(url="/cargo_addition/next", files={})
        self.assertEqual(status, 422)
        status, _ = await self.create(url="/cargo_addition/next")
        self.assertEqual(status, 303)
        draft = self.session.execute(select(Cargo)).scalar_one()
        self.assertEqual(draft.publication_status, "draft")
        self.assertTrue(draft.image_url.startswith("image-"))
        self.assertTrue(draft.video_url.startswith("video-"))

    def test_openapi_ten_methods_and_three_required_create_fields(self):
        schema = app.openapi()
        methods = [
            (path, method) for path, operations in schema["paths"].items()
            if path.startswith("/api/") for method in operations
            if method in {"get", "post", "put", "delete", "patch"}
        ]
        self.assertEqual(len(methods), 10)
        ref = schema["paths"]["/api/cargos"]["post"]["requestBody"]["content"]["multipart/form-data"]["schema"]["$ref"]
        create_schema = schema["components"]["schemas"][ref.split("/")[-1]]
        self.assertEqual(set(create_schema["properties"]), {"cargo_name", "image", "video"})
        self.assertEqual(set(create_schema["required"]), {"cargo_name", "image", "video"})


if __name__ == "__main__":
    unittest.main()
