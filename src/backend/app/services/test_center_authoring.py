"""受限自然语言编译与独立测试资产；未知意图只保存为待澄清草稿。"""

import json
import time
import uuid

from app.services.test_center import digest, encode


def lines(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 50:
        raise ValueError("输入和断言各需要 1–50 行")
    if any(not isinstance(v, str) or not v.strip() or len(v) > 8000 for v in value):
        raise ValueError("每行需要非空文字，最多 8000 字")
    return [v.strip() for v in value]


class Authoring:
    def __init__(self, center):
        self.center = center
        with center.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS drafts (id TEXT PRIMARY KEY, created REAL NOT NULL,
                    payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reviews (id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
                    case_id TEXT NOT NULL, created REAL NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS contexts (id TEXT PRIMARY KEY, created REAL NOT NULL,
                    payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS calls (id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
                    created REAL NOT NULL, payload TEXT NOT NULL);
                PRAGMA user_version=2;
            """)

    def drafts(self):
        with self.center.db() as db:
            return [
                json.loads(r[0])
                for r in db.execute("SELECT payload FROM drafts ORDER BY created DESC LIMIT 100")
            ]

    def compile(self, body):
        title = str(body.get("title", "")).strip()
        if not title or len(title) > 160:
            raise ValueError("名称需要 1–160 字")
        inputs, assertions = lines(body.get("inputs")), lines(body.get("assertions"))
        catalog = self.center.catalog()
        template = next(
            (
                c
                for c in catalog["cases"]
                if c["id"] == body.get("template_id") and c["available"] and not c["archived"]
            ),
            None,
        )
        issues = []
        case_id = body.get("case_id") or "custom-" + uuid.uuid4().hex[:16]
        existing = next((c for c in catalog["cases"] if c["id"] == case_id), None)
        if existing and body.get("base_revision") != existing["revision"]:
            raise ValueError("用例已有新修订，请重新打开后编辑")
        definition = {
            "id": case_id,
            "title": title,
            "module": "管理员用例",
            "kind": body.get("kind"),
            "origin": "authored",
            "inputs": inputs,
            "assertions": assertions,
            "core": existing["core"] if existing else False,
            "targets": [],
            "timeout": 600,
        }
        provenance = (existing or template or {}).get("definition", {})
        definition["purpose"] = (
            body.get("purpose")
            if body.get("purpose") is not None
            else provenance.get("purpose", title)
        )
        definition["sources"] = provenance.get("sources", [])
        if body.get("kind") in {"api", "ui"}:
            if not template or template["definition"]["kind"] != body["kind"]:
                issues.append("请选择一个已登记的同类型动作模板")
            else:
                base = template["definition"]
                composed = body["kind"] == "ui" and (
                    base.get("targets") == ["scenario"]
                    or inputs != base["inputs"]
                    or assertions != base["assertions"]
                )
                if composed:
                    from app.services.test_center_steps import compile_ui

                    definition.update(
                        compile_ui(body, base.get("fixture", base["targets"][0]), issues)
                    )
                    definition.update(
                        module=base["module"],
                        template_id=template["id"],
                        template_revision=template["revision"],
                    )
                # 不用关键词相似度把未知预期偷换成已知测试；模板完整执行，其覆盖范围明确展示。
                for field, values in (
                    () if composed else (("inputs", inputs), ("assertions", assertions))
                ):
                    allowed = base[field]
                    for value in values:
                        if value not in allowed:
                            issues.append(
                                f"未支持的{'操作' if field == 'inputs' else '断言'}：{value}"
                            )
                    if set(values) != set(allowed):
                        issues.append("当前模板需要保留其完整操作和断言；新动作请登记实现后再运行")
                if not composed:
                    definition.update(
                        targets=base["targets"],
                        timeout=base["timeout"],
                        module=base["module"],
                        template_id=template["id"],
                        template_revision=template["revision"],
                    )
        elif body.get("kind") == "ai":
            from app.services.test_center_ai import compile_ai

            definition.update(compile_ai(self.center, body, issues))
        else:
            issues.append("测试类型必须是 API、UI 或 AI")
        draft = {
            "id": uuid.uuid4().hex,
            "created": time.time(),
            "state": "needs_clarification" if issues else "ready",
            "issues": issues,
            "definition": definition,
            "base_revision": body.get("base_revision"),
            "compiler": "allowlist-v1",
            "generation_calls": 0,
        }
        if not issues:
            self.center.validate(definition)
        with self.center.db() as db:
            db.execute(
                "INSERT INTO drafts VALUES(?,?,?)",
                (draft["id"], draft["created"], encode(draft)),
            )
        return draft

    def save(self, draft_id):
        with self.center.db() as db:
            row = db.execute("SELECT payload FROM drafts WHERE id=?", (draft_id,)).fetchone()
            if not row:
                raise KeyError(draft_id)
            draft = json.loads(row[0])
            if draft["state"] != "ready":
                raise ValueError("草稿仍有待澄清项，不能保存为可执行用例")
            value = draft["definition"]
            self.center.validate(value)
            revision = digest(value)
            row = db.execute("SELECT revision FROM cases WHERE id=?", (value["id"],)).fetchone()
            if row and row[0] == revision:
                return {"id": value["id"], "revision": revision}
            if row and row[0] != draft.get("base_revision"):
                raise ValueError("用例已有新修订，请重新生成草稿")
            if not row and draft.get("base_revision"):
                raise ValueError("原用例不存在")
            db.execute("INSERT OR IGNORE INTO revisions VALUES(?,?)", (revision, encode(value)))
            db.execute(
                """INSERT INTO cases(id,revision,definition,core) VALUES(?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,definition=excluded.definition""",
                (value["id"], revision, encode(value), int(value["core"])),
            )
            db.execute(
                "INSERT INTO events VALUES(?,?)",
                (
                    time.time(),
                    encode(
                        {
                            "event": "save_case",
                            "case_id": value["id"],
                            "revision": revision,
                            "draft": draft_id,
                        }
                    ),
                ),
            )
        return {"id": value["id"], "revision": revision}

    def revisions(self, case_id):
        with self.center.db() as db:
            return [
                {"revision": r[0], "definition": json.loads(r[1])}
                for r in db.execute("SELECT * FROM revisions")
                if json.loads(r[1])["id"] == case_id
            ]

    def review(self, run_id, body, reviewer):
        run = self.center.get_run(run_id)
        case = next((c for c in run["cases"] if c["id"] == body["case_id"]), None)
        if not case or case["status"] in {"queued", "running"}:
            raise ValueError("只能复核已结束的测试")
        attempts = case.get("attempts", [])
        if not 0 <= body["attempt"] < len(attempts):
            raise ValueError("目标测试次数不存在")
        if not body["reason"].strip():
            raise ValueError("请填写复核依据")
        record = {
            **body,
            "id": uuid.uuid4().hex,
            "run_id": run_id,
            "created": time.time(),
            "reviewer": reviewer,
            "revision": case["revision"],
            "automated_status": attempts[body["attempt"]]["status"],
        }
        with self.center.db() as db:
            db.execute(
                "INSERT INTO reviews VALUES(?,?,?,?,?)",
                (record["id"], run_id, case["id"], record["created"], encode(record)),
            )
        return record
