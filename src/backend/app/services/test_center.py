"""固定用例、构建快照和运行记录的公开服务。只接收登记用例 ID。"""

import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ACTIVE = {"queued", "running"}
EXCLUDED = {
    "node_modules",
    ".next",
    "__pycache__",
    ".pytest_cache",
    "data",
    "logs",
    "reports",
    "certs",
    "generated",
    "savepoints_registry.json",
    "generated_index.json",
}
SOURCE_DIRS = (
    "scripts",
    "src/backend/app",
    "src/backend/scripts",
    "src/backend/alembic",
    "src/frontend",
    "test/backend",
    "test_agent",
)
SOURCE_FILES = (
    "pytest.ini",
    "src/backend/pyproject.toml",
    "src/backend/alembic.ini",
    "src/backend/requirements.lock",
)


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def source_files(root: Path):
    """仅复制受信任源码；不遍历符号链接、运行数据、环境文件和凭据。"""

    def walk(directory):
        if not directory.is_dir() or directory.is_symlink():
            return
        for path in sorted(directory.iterdir()):
            if path.is_symlink() or path.name in EXCLUDED or path.name.startswith(".env"):
                continue
            if path.is_dir():
                yield from walk(path)
            elif path.suffix not in {".pyc", ".db", ".pem", ".key", ".log"}:
                yield path

    for directory in SOURCE_DIRS:
        yield from walk(root / directory)
    for filename in SOURCE_FILES:
        path = root / filename
        if path.is_file() and not path.is_symlink():
            yield path


def storage_bytes(root: Path) -> int:
    total = 0
    for path in root.rglob("*"):
        try:
            if path.is_file() and not path.is_symlink():
                total += path.stat().st_size
        except FileNotFoundError:
            # 运行副本可能在统计同时完成清理。
            continue
    return total


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


class TestCenter:
    __test__ = False

    def __init__(self, source_root: Path, control_root: Path):
        self.source = source_root.resolve()
        self.root = control_root.resolve()
        if self.root == self.source or any(
            self.root.is_relative_to(self.source / path) for path in (*SOURCE_DIRS, "data")
        ):
            raise ValueError(
                "测试控制存储必须放在源码快照范围和业务 data 之外，避免递归复制运行副本"
            )
        self.root.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            if db.execute("PRAGMA user_version").fetchone()[0] > 2:
                raise ValueError("测试控制库版本更新，请使用匹配的执行器")
            # 独立控制库初始迁移 v1，不修改业务数据库。
            db.executescript("""
                CREATE TABLE IF NOT EXISTS cases (id TEXT PRIMARY KEY, revision TEXT NOT NULL,
                    definition TEXT NOT NULL, core INTEGER NOT NULL, archived INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, status TEXT NOT NULL,
                    created REAL NOT NULL, cancel INTEGER NOT NULL DEFAULT 0, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS revisions (revision TEXT PRIMARY KEY, definition TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (created REAL NOT NULL, payload TEXT NOT NULL);
            """)

        from app.services.test_center_authoring import Authoring

        self.authoring = Authoring(self)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.root / "control.sqlite3", timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def catalog(self) -> dict[str, Any]:
        definitions = []
        for path in sorted((self.source / "test_agent/catalog").glob("*.json")):
            value = json.loads(path.read_text())
            self.validate(value)
            if path.stem != value["id"]:
                raise ValueError("用例文件名必须与 ID 一致")
            definitions.append(value)
        ids = [value["id"] for value in definitions]
        if len(ids) != len(set(ids)):
            raise ValueError("用例 ID 重复")
        with self.db() as db:
            for value in definitions:
                revision = digest(value)
                db.execute(
                    "INSERT OR IGNORE INTO revisions VALUES(?,?)",
                    (revision, encode(value)),
                )
                existing = db.execute(
                    "SELECT definition FROM cases WHERE id=?", (value["id"],)
                ).fetchone()
                if existing and json.loads(existing[0]).get("origin") == "authored":
                    continue
                db.execute(
                    """INSERT INTO cases(id, revision, definition, core) VALUES(?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET revision=excluded.revision, definition=excluded.definition""",
                    (
                        value["id"],
                        revision,
                        encode(value),
                        int(value.get("core", False)),
                    ),
                )
            cases = []
            for row in db.execute("SELECT * FROM cases ORDER BY id"):
                case = dict(row)
                case["core"] = bool(case["core"])
                case["archived"] = bool(case["archived"])
                case["definition"] = json.loads(case["definition"])
                case["available"] = (
                    case["id"] in ids or case["definition"].get("origin") == "authored"
                )
                upstream = next((v for v in definitions if v["id"] == case["id"]), None)
                if upstream and case["definition"].get("origin") == "authored":
                    case["upstream"] = {
                        "revision": digest(upstream),
                        "definition": upstream,
                    }
                cases.append(case)
        sha = git(self.source, "rev-parse", "HEAD") or "unknown"
        tag = git(self.source, "describe", "--tags", "--abbrev=0")
        exact_tag = git(self.source, "describe", "--tags", "--exact-match")
        dirty = bool(git(self.source, "status", "--porcelain")) or sha == "unknown"
        changes = [
            json.loads(p.read_text())
            for p in sorted((self.source / "test_agent/changes").glob("*.json"))
        ]
        previous = (
            git(self.source, "describe", "--tags", "--abbrev=0", "HEAD^") if exact_tag else tag
        )
        changed = (
            git(self.source, "diff", "--name-only", previous, "HEAD").splitlines()
            if previous
            else []
        )
        changed += git(self.source, "diff", "--name-only", "HEAD").splitlines()
        changed += git(self.source, "ls-files", "--others", "--exclude-standard").splitlines()
        version_ids = set()
        covered = set()
        for change in changes:
            # 只归集当前增量触达的变更，历史清单不会永远进入每个新版本。
            paths = change.get("paths", [])
            touched = {p for p in changed if any(p.startswith(prefix) for prefix in paths)}
            if touched:
                covered.update(touched)
                version_ids.update(change.get("cases", []))
        gaps = [
            p
            for p in sorted(set(changed) - covered)
            if p.startswith(("src/backend/app/", "src/frontend/"))
        ]
        for case in cases:
            case["version"] = case["id"] in version_ids
        return {
            "cases": cases,
            "build": {
                "sha": sha,
                "tag": exact_tag,
                "base_tag": previous,
                "label": (
                    exact_tag if exact_tag and not dirty else f"{tag or '未打 tag'} · 开发中"
                ),
                "dirty": dirty,
            },
            "changes": changes,
            "coverage_gaps": gaps,
            "unknown_cases": sorted(version_ids - set(ids)),
            "worker": self.worker_status(),
            "storage": {
                "free_bytes": shutil.disk_usage(self.root).free,
                "used_bytes": storage_bytes(self.root),
            },
        }

    def validate(self, value: dict[str, Any]) -> None:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", value.get("id", "")):
            raise ValueError("无效用例 ID")
        if value.get("kind") not in {"api", "ui", "ai"}:
            raise ValueError("只运行登记的 API/UI/AI 用例")
        if not value.get("inputs") or not value.get("assertions"):
            raise ValueError("用例必须分别填写输入和断言")
        if not 1 <= value.get("timeout", 180) <= 1800:
            raise ValueError("超时必须在 1–1800 秒之间")
        targets = value.get("targets", [])
        if value["kind"] == "ui" and targets == ["scenario"]:
            from app.services.test_center_steps import compile_ui

            issues = []
            compiled = compile_ui(value, value.get("fixture"), issues)
            if issues or any(compiled[key] != value.get(key) for key in ("steps", "ui_checks")):
                raise ValueError("浏览器执行步骤与输入/断言不一致或尚未支持")
            return
        if value["kind"] == "ai":
            from app.services.test_center_ai import compile_ai, get_context

            get_context(self, value.get("context_id"))
            if (
                not value.get("checks")
                or targets != ["ai-replay"]
                or not 1 <= value.get("repeats", 1) <= 10
            ):
                raise ValueError("AI 用例缺少有效断言或重复次数")
            issues = []
            compiled = compile_ai(self, value, issues)
            if issues or compiled["checks"] != value["checks"]:
                raise ValueError("AI 执行断言与文字标准不一致或未支持")
            if value.get("conversation_mode") == "workflow" and compiled["steps"] != value.get(
                "steps"
            ):
                raise ValueError("业务执行步骤与输入不一致")
            return
        if not targets:
            raise ValueError("缺少执行入口")
        for target in targets:
            filename = target.split("::")[0]
            if value["kind"] == "api":
                if not re.fullmatch(r"test/backend/test_[\w]+\.py(?:::[\w\[\]-]+)*", target):
                    raise ValueError("只允许固定的后端测试入口")
            elif target not in {
                "home",
                "admin-center",
                "chat",
                "reply-integrity",
                "rumination",
                "account",
                "desktop",
            }:
                raise ValueError("未知浏览器测试套件")
            if value["kind"] == "api" and not (self.source / filename).is_file():
                raise ValueError(f"测试文件不存在: {filename}")

    def set_case(self, case_id: str, *, core: bool, archived: bool) -> dict[str, Any]:
        self.catalog()
        with self.db() as db:
            if not db.execute(
                "UPDATE cases SET core=?, archived=? WHERE id=?",
                (core, archived, case_id),
            ).rowcount:
                raise KeyError(case_id)
            db.execute(
                "INSERT INTO events VALUES(?,?)",
                (
                    time.time(),
                    encode({"case_id": case_id, "core": core, "archived": archived}),
                ),
            )
        return {"id": case_id, "core": core, "archived": archived}

    def enqueue(self, case_ids: list[str], mode: str = "diagnostic", budget=None) -> dict[str, Any]:
        catalog = self.catalog()
        available = {c["id"]: c for c in catalog["cases"] if c["available"] and not c["archived"]}
        required = sorted(c["id"] for c in available.values() if c["core"] or c["version"])
        selected = list(dict.fromkeys(case_ids))
        if not selected or any(key not in available for key in selected):
            raise ValueError("请选择存在且未归档的用例")
        ai_cases = [
            available[key] for key in selected if available[key]["definition"]["kind"] == "ai"
        ]
        ai = None
        if ai_cases:
            from app.services.test_center_budget import prepare

            ai = prepare(self, ai_cases, budget)
        if mode not in {"diagnostic", "release"}:
            raise ValueError("未知运行模式")
        if mode == "release" and (
            sorted(selected) != required
            or catalog["build"]["dirty"]
            or not catalog["build"]["tag"]
            or catalog["coverage_gaps"]
            or catalog["unknown_cases"]
        ):
            raise ValueError("发布验收要求干净 tag、完整核心/版本清单且无覆盖缺口")
        if shutil.disk_usage(self.root).free < 512 * 1024 * 1024:
            raise ValueError("剩余空间不足 512 MiB，停止接收新任务；请人工整理历史")
        run_id = uuid.uuid4().hex
        folder = self.root / "runs" / run_id
        snapshot = folder / "source"
        snapshot.mkdir(parents=True)
        hashes = {}
        try:
            for path in source_files(self.source):
                relative = path.relative_to(self.source)
                data = path.read_bytes()
                destination = snapshot / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
                hashes[str(relative)] = hashlib.sha256(data).hexdigest()
            # 复制过程中源码变化必须拒绝，避免用例定义与实际执行的源码不一致。
            after = {
                str(p.relative_to(self.source)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in source_files(self.source)
            }
            if hashes != after:
                raise ValueError("源码正在变化，请保存完成后重新运行")
            current_sha = git(self.source, "rev-parse", "HEAD") or "unknown"
            current_dirty = (
                bool(git(self.source, "status", "--porcelain")) or current_sha == "unknown"
            )
            if current_sha != catalog["build"]["sha"] or current_dirty != catalog["build"]["dirty"]:
                raise ValueError("Git 构建状态正在变化，请完成保存/提交后重试")
            for key in selected:
                if available[key]["definition"].get("origin") == "authored":
                    continue
                current = json.loads((snapshot / "test_agent/catalog" / f"{key}.json").read_text())
                if digest(current) != available[key]["revision"]:
                    raise ValueError("登记与快照不一致，请刷新用例库")
            payload = {
                "id": run_id,
                "status": "queued",
                "mode": mode,
                "created": time.time(),
                "build": {**catalog["build"], "source_digest": digest(hashes)},
                "manifest_digest": digest(
                    [(key, available[key]["revision"]) for key in sorted(selected)]
                ),
                "required": required,
                "cases": [{**available[key], "status": "queued"} for key in selected],
            }
            if ai:
                payload["ai"] = ai
            (folder / "source-hashes.json").write_text(encode(hashes))
            with self.db() as db:
                if (
                    db.execute(
                        "SELECT count(*) FROM runs WHERE status IN ('queued','running')"
                    ).fetchone()[0]
                    >= 20
                ):
                    raise ValueError("队列已满，请等待已有批次完成")
                db.execute(
                    "INSERT INTO runs VALUES(?,?,?,?,?)",
                    (run_id, "queued", payload["created"], 0, encode(payload)),
                )
            return payload
        except Exception:
            shutil.rmtree(folder)
            raise

    def list_runs(self) -> list[dict[str, Any]]:
        from app.services.test_center_budget import evidence

        with self.db() as db:
            return [
                evidence(self, json.loads(row[0]), compact=True)
                for row in db.execute("SELECT payload FROM runs ORDER BY created DESC LIMIT 100")
            ]

    def get_run(self, run_id: str) -> dict[str, Any]:
        from app.services.test_center_budget import evidence

        with self.db() as db:
            row = db.execute("SELECT payload FROM runs WHERE id=?", (run_id,)).fetchone()
            if not row:
                raise KeyError(run_id)
            return evidence(self, json.loads(row[0]))

    def cancel(self, run_id: str) -> dict[str, Any]:
        with self.db() as db:
            if not db.execute("UPDATE runs SET cancel=1 WHERE id=?", (run_id,)).rowcount:
                raise KeyError(run_id)
        return self.get_run(run_id)

    def cancelled(self, run_id: str) -> bool:
        with self.db() as db:
            return bool(db.execute("SELECT cancel FROM runs WHERE id=?", (run_id,)).fetchone()[0])

    def save_run(self, run: dict[str, Any]) -> None:
        with self.db() as db:
            db.execute(
                "UPDATE runs SET status=?, payload=? WHERE id=?",
                (run["status"], encode(run), run["id"]),
            )

    def worker_status(self) -> dict[str, Any]:
        path = self.root / "heartbeat.json"
        try:
            value = json.loads(path.read_text())
            return {**value, "ready": time.time() - value["time"] < 15}
        except (OSError, ValueError):
            return {"ready": False}

    def artifact(self, run_id: str, case_id: str, name: str) -> Path:
        run = self.get_run(run_id)
        case = next((c for c in run["cases"] if c["id"] == case_id), None)
        if not case or name not in case.get("artifacts", []):
            raise KeyError(name)
        directory = self.root / "runs" / run_id / "artifacts" / case_id
        path = directory / name
        if (
            path.is_symlink()
            or not path.is_file()
            or not path.resolve().is_relative_to(directory.resolve())
        ):
            raise KeyError(name)
        return path
