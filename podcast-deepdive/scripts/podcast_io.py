#!/usr/bin/env python3
"""podcast_io.py — общая атомарная запись JSON для скриптов podcast-конвейера.

stdlib-only. Атомарная запись: временный файл в каталоге
назначения → fsync → сохранение прав → os.replace. Частичная запись не может
оставить назначение в испорченном состоянии.
"""
import json
import os
import stat
import tempfile


def atomic_write_json(value, destination):
    """Сериализовать value и атомарно заменить destination."""
    destination = os.path.abspath(destination)
    payload = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    mode = (
        stat.S_IMODE(os.stat(destination).st_mode)
        if os.path.exists(destination)
        else 0o644
    )
    fd, tmp = tempfile.mkstemp(
        prefix="." + os.path.basename(destination) + ".",
        suffix=".tmp",
        dir=os.path.dirname(destination) or ".",
    )
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, destination)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
