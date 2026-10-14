"""源端脱敏导出与安全导入。只接受已经停写取得的完成备份，不操作在线服务。"""

import hashlib
import json
import os
import shutil
import sqlite3
import tarfile
import tempfile
import time
from pathlib import Path, PurePosixPath

from test_agent.snapshot.sanitize import Sanitizer

MAX_BYTES = 8 * 1024**3
MAX_FILES = 200000
BUSINESS_DIRS = {"simple", "user", "conversations", "question_progress"}
TEXT_SUFFIXES = {".json", ".jsonl", ".md", ".txt"}


def sha(path):
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def fresh_directory(path):
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise ValueError("目标已经存在，拒绝覆盖")
    path.mkdir(parents=True, mode=0o700)
    return path


def safe_files(root):
    if root.is_symlink():
        raise ValueError("快照根目录不能是符号链接")
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError("快照不允许符号链接或特殊文件")
        if path.is_file():
            yield path


def decode(path):
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return json.loads(text)
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    return text


def export_snapshot(backup, output, *, secret, policy=None):
    backup, output = Path(backup).resolve(), Path(output).absolute()
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(backup):
        raise ValueError("导出目标已存在或位于备份内")
    if not (backup / "BACKUP_COMPLETE").is_file() or not (backup / "data").is_dir():
        raise ValueError("只接受包含 BACKUP_COMPLETE 的一致 DB＋data 备份")
    database = backup / "database.sqlite"
    if not database.is_file() or database.is_symlink():
        raise ValueError("备份 database.sqlite 缺失或为链接")
    if any(Path(str(database) + suffix).exists() for suffix in ("-wal", "-journal")):
        raise ValueError("导出源仍带 SQLite 写入日志，请先取得关闭完成的独立备份")
    files = list(safe_files(backup / "data"))
    before = {str(p.relative_to(backup)): sha(p) for p in [database, *files]}
    scrub = Sanitizer(secret, policy)
    selected, excluded = [], {"binary": 0, "outside_business": 0, "lock": 0}
    for path in files:
        relative = path.relative_to(backup / "data")
        if relative.parts[0] not in BUSINESS_DIRS:
            excluded["outside_business"] += 1
        elif path.suffix == ".lock":
            excluded["lock"] += 1
        elif path.suffix.lower() not in TEXT_SUFFIXES:
            excluded["binary"] += 1
        else:
            value = decode(path)
            scrub.discover(value)
            selected.append((path, value))
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".snapshot-export-", dir=output.parent) as temporary:
        target = Path(temporary)
        db_copy = target / "database.sqlite"
        with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as source:
            tables = scrub.inspect_database(source)
            with sqlite3.connect(db_copy) as destination:
                source.backup(destination)
        scrub.database(db_copy, tables)
        for path, value in selected:
            # 固定目录/文件名保持不变；动态邮箱、激活码或外部标识才做同一映射。
            relative = Path(
                *(scrub.key_mapping.get(part, part) for part in path.relative_to(backup).parts)
            )
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("脱敏文件路径越界")
            dest = target / relative
            if dest.exists():
                raise ValueError("脱敏后文件名冲突")
            dest.parent.mkdir(parents=True, exist_ok=True)
            clean = scrub.clean(value)
            if path.suffix == ".jsonl":
                dest.write_text(
                    "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in clean)
                )
            elif path.suffix == ".json":
                write_json(dest, clean)
            else:
                dest.write_text(clean)
        after = {
            str(p.relative_to(backup)): sha(p) for p in [database, *safe_files(backup / "data")]
        }
        if before != after:
            raise ValueError("源备份仍在变化，拒绝导出不一致快照")
        exported = list(safe_files(target))
        manifest = {
            "format": 1,
            "created_at": time.time(),
            "privacy": "pseudonymized-restricted",
            "free_text_review_required": True,
            "external_ai_allowed": False,
            "excluded_files": excluded,
            "files": {
                str(p.relative_to(target)): {"sha256": sha(p), "size": p.stat().st_size}
                for p in exported
            },
        }
        write_json(target / "manifest.json", manifest)
        partial = target / "archive.tar.gz"
        with tarfile.open(partial, "w:gz") as archive:
            for path in [*exported, target / "manifest.json"]:
                info = archive.gettarinfo(str(path), str(path.relative_to(target)))
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mode = 0o600
                with path.open("rb") as stream:
                    archive.addfile(info, stream)
        # 独占创建，不能在并发导出时覆盖另一份成品。
        with output.open("xb") as stream, partial.open("rb") as source:
            os.chmod(output, 0o600)
            shutil.copyfileobj(source, stream)
    return manifest


def import_snapshot(archive_path, destination):
    destination = fresh_directory(destination)
    try:
        total, names = 0, set()
        with tarfile.open(archive_path, "r:gz") as archive:
            for member in archive:
                relative = PurePosixPath(member.name)
                allowed_data = (
                    len(relative.parts) >= 3
                    and relative.parts[0] == "data"
                    and relative.parts[1] in BUSINESS_DIRS
                    and relative.suffix in TEXT_SUFFIXES
                    and not any(part.startswith(".") for part in relative.parts)
                )
                if (
                    not member.isfile()
                    or relative.is_absolute()
                    or ".." in relative.parts
                    or "\\" in member.name
                    or member.name in names
                    or str(relative) != member.name
                    or not (member.name in {"database.sqlite", "manifest.json"} or allowed_data)
                ):
                    raise ValueError("传输包含非法路径、链接、重复或非业务文件")
                total += member.size
                names.add(member.name)
                if total > MAX_BYTES or len(names) > MAX_FILES:
                    raise ValueError("传输包超过大小或文件数限制")
                target = destination / member.name
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
        verify_snapshot(destination)
        return json.loads((destination / "manifest.json").read_text())
    except BaseException:
        shutil.rmtree(destination)
        raise


def verify_snapshot(root):
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text())
    if manifest.get("format") != 1 or manifest.get("privacy") != "pseudonymized-restricted":
        raise ValueError("不是受支持的脱敏快照")
    actual = {str(p.relative_to(root)) for p in safe_files(root)} - {"manifest.json"}
    if actual != set(manifest["files"]) or "database.sqlite" not in actual:
        raise ValueError("快照文件清单不一致")
    for name, info in manifest["files"].items():
        path = root / name
        if path.stat().st_size != info["size"] or sha(path) != info["sha256"]:
            raise ValueError("快照校验失败")
    return manifest


def capture_snapshot(database, data, output, *, writers_stopped=False):
    """运维已停全部写入后调用；本工具自身不会停止或重启生产服务。"""
    database, data, output = Path(database).resolve(), Path(data).resolve(), Path(output).absolute()
    if not writers_stopped:
        raise ValueError("必须先停止应用及后台写入，再显式指定 --writers-stopped")
    if not database.is_file() or not data.is_dir():
        raise ValueError("实际数据库或 data 目录不存在")
    if output.resolve().is_relative_to(data) or database.is_relative_to(output.resolve()):
        raise ValueError("备份输出与源数据重叠")
    files = list(safe_files(data))
    sidecars = [Path(str(database) + suffix) for suffix in ("-wal", "-shm", "-journal")]
    watched = [database, *(p for p in sidecars if p.exists()), *files]
    before = {str(path): sha(path) for path in watched}
    destination = fresh_directory(output)
    try:
        with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as source:
            with sqlite3.connect(destination / "database.sqlite") as target:
                source.backup(target)
                if target.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                    raise ValueError("备份数据库完整性失败")
        shutil.copytree(data, destination / "data")
        after_files = [database, *(p for p in sidecars if p.exists()), *safe_files(data)]
        if before != {str(path): sha(path) for path in after_files}:
            raise ValueError("备份期间源数据发生变化；请确认所有写入均已停止")
        write_json(
            destination / "capture.json",
            {
                "format": 1,
                "created_at": time.time(),
                "consistency": "operator-quiesced-and-change-checked",
            },
        )
        (destination / "BACKUP_COMPLETE").touch()
    except BaseException:
        shutil.rmtree(destination)
        raise
    return destination
