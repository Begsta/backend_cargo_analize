"""Копирует выбранную видеозаглушку из MinIO в локальную статику."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.storage import get_minio  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", default="media")
    parser.add_argument("--object", default="gemini_generated_video_076b54a8.mp4")
    args = parser.parse_args()
    target = (
        Path(__file__).resolve().parents[1]
        / "cargo_front/static/vid/gemini_generated_video_076b54a8.mp4"
    )
    if target.exists():
        parser.exit(1, f"Файл уже существует, перезапись отменена: {target}\n")
    target.parent.mkdir(parents=True, exist_ok=True)
    client = get_minio()
    client.fget_object(args.bucket, args.object, str(target))
    print(f"Видео скопировано: {args.bucket}/{args.object} -> {target}")


if __name__ == "__main__":
    main()
