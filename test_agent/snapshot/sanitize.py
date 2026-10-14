"""确定性假名化。保留业务关系；自由文本仍属于受限资料，不声称完全匿名。"""

import hashlib
import hmac
import json
import re
import sqlite3
from pathlib import Path

EMAIL = re.compile(r"[\w.+%-]+@[\w.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")
IDENTITY = re.compile(r"(?<!\w)\d{17}[0-9Xx](?!\w)")
URL = re.compile(r"https?://[^\s<>\"'）)]+")
TOKEN = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{8,}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\b"
)
SECRET = re.compile(
    r"password|passwd|secret|(?:^|_)(?:access_token|refresh_token|token|token_hash|id_token)(?:$|_)|api_key|private_key|credential|cookie",
    re.I,
)
NAMES = {
    "username",
    "nickname",
    "real_name",
    "full_name",
    "name",
    "姓名",
    "昵称",
    "contact",
    "company",
    "address",
    "company_name",
    "education_school",
}
CODES = {
    "activation_code",
    "coupon_code",
    "code",
    "consumed_into",
    "upgraded_from_code",
    "forked_from_code",
    "frozen_activation_code",
}
PRIVATE_IDS = {
    "trade_no",
    "out_trade_no",
    "buyer_id",
    "agreement_no",
    "channel_refund_no",
    "device_id",
    "visitor_id",
    "ip",
    "ip_address",
    "client_ip",
    "oss_key",
}
EMPTY_TABLES = {"refresh_tokens"}
STRUCTURAL = {
    "status",
    "mode",
    "role",
    "phase",
    "step",
    "current_step",
    "category",
    "type",
    "code_type",
    "package_type",
    "plan_type",
    "membership_plan",
    "user_type",
    "version_num",
    "provider",
    "model",
    "scene",
    "channel",
    "currency",
    "review_status",
}


def quote(value):
    return '"' + value.replace('"', '""') + '"'


class Sanitizer:
    def __init__(self, secret, policy=None):
        if len(secret) < 32:
            raise ValueError("脱敏密钥至少 32 字节，保存在生产侧，不进入传输包")
        self.secret = secret
        self.policy = policy or {}
        self.mapping = {}
        self.key_mapping = {}
        self._pattern = None
        self.schema = json.loads(Path(__file__).with_name("schema.json").read_text())
        self.schema.update(self.policy.get("extra_schema", {}))
        for value in self.policy.get("redact_literals", []):
            if not isinstance(value, str) or len(value) < 2:
                raise ValueError("附加脱敏词必须至少两个字符")
            self.mapping[value] = self.alias("text", value)

    def alias(self, kind, value):
        token = hmac.new(self.secret, f"{kind}:{value}".encode(), hashlib.sha256).hexdigest()[:20]
        if kind == "email":
            return f"u{token}@example.invalid"
        if kind == "phone":
            return "T" + token[:18]
        if kind == "code":
            # 保留新/旧码的输入格式，避免脱敏改变归一化分支、掩盖历史兼容问题。
            prefix = next((p for p in ("OPENLIFE-", "Q-", "SBX", "ADM") if value.startswith(p)), "")
            alphabet = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
            material = hmac.new(
                self.secret, ("code-body:" + value).encode(), hashlib.sha256
            ).digest()
            body = "".join(
                "-" if char == "-" else alphabet[material[index % len(material)] % len(alphabet)]
                for index, char in enumerate(value[len(prefix) :])
            )
            return prefix + body
        return f"测试{kind}_{token[:12]}"

    def discover(self, value, key=""):
        if isinstance(value, dict):
            for name, item in value.items():
                self.discover(item, name)
        elif isinstance(value, list):
            for item in value:
                self.discover(item, key)
        elif isinstance(value, str) and value:
            kind = None
            if SECRET.search(key):
                kind = "secret"
            elif "email" in key.lower() or "邮箱" in key:
                kind = "email"
            elif "phone" in key.lower() or key in {"mobile", "电话", "手机号"}:
                kind = "phone"
            elif key.lower() in NAMES:
                kind = "name"
            elif key.lower() in CODES:
                kind = "code"
            elif key.lower() in PRIVATE_IDS:
                kind = "reference"
            if kind:
                self.mapping[value] = self.alias(kind, value) if kind != "secret" else "!disabled"
                if kind in {"code", "email", "reference"}:
                    self.key_mapping[value] = self.mapping[value]
                # 关联码/邮箱的固定映射不能被同名昵称覆盖。
                if value in self.key_mapping:
                    self.mapping[value] = self.key_mapping[value]
                self._pattern = None
            if value[:1] in ("{", "["):
                try:
                    self.discover(json.loads(value))
                except json.JSONDecodeError:
                    pass

    def text(self, value):
        # 一个替换过程避免重复替换假名；最长词优先，避免姓名/完整邮箱的前缀冲突。
        if self.mapping:
            if self._pattern is None:
                self._pattern = re.compile(
                    "|".join(
                        (
                            (r"(?<![A-Za-z0-9])" + re.escape(k) + r"(?![A-Za-z0-9])")
                            if k.isascii() and k.isalnum()
                            else re.escape(k)
                        )
                        for k in sorted(self.mapping, key=len, reverse=True)
                    )
                )
            value = self._pattern.sub(lambda m: self.mapping[m.group()], value)
        value = EMAIL.sub(
            lambda m: (
                m.group()
                if m.group().endswith("@example.invalid")
                else self.alias("email", m.group())
            ),
            value,
        )
        value = PHONE.sub(lambda m: self.alias("phone", m.group()), value)
        value = IDENTITY.sub("[证件已脱敏]", value)
        value = TOKEN.sub("[凭据已清除]", value)
        return URL.sub("https://redacted.invalid", value)

    def clean(self, value, key=""):
        if value is None:
            return None
        if SECRET.search(key):
            return "!disabled" if isinstance(value, str) else None
        if key in {"workspace_root", "sandbox_root"} and value:
            path = Path(str(value))
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("工作区路径越界，拒绝导出")
        if key in {
            "report_id",
            "session_id",
            "thread_id",
            "combo_id",
            "user_id",
            "activation_session_id",
            "owner_user_id",
        } and isinstance(value, str):
            if "/" in value or "\\" in value or value in {".", ".."}:
                raise ValueError("业务标识包含路径字符，拒绝导出")
        if isinstance(value, dict):
            result = {}
            for name, item in value.items():
                # 只重映射激活码/邮箱等动态键，不能把恰好与昵称相同的业务字段名改掉。
                new_name = self.key_mapping.get(name, name)
                if new_name in result:
                    raise ValueError("脱敏后 JSON 键冲突")
                result[new_name] = self.clean(item, name)
            return result
        if isinstance(value, list):
            return [self.clean(item, key) for item in value]
        if isinstance(value, str):
            # 枚举、时间和内部 UUID 不按昵称替换，保持业务分支及关联关系。
            if (
                key in STRUCTURAL
                or key.endswith("_at")
                or key in {"state", "stage", "source"}
                or key.endswith(("_state", "_status", "_type"))
                or ((key == "id" or key.endswith("_id")) and key not in PRIVATE_IDS)
                or (
                    re.search(r"amount|price|fee|cost|quantity|count|tokens|rate|balance", key)
                    and re.fullmatch(r"[+-]?\d+(?:\.\d+)?", value)
                )
                or re.fullmatch(
                    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
                    value,
                )
            ):
                return value
            if value[:1] in ("{", "["):
                try:
                    return json.dumps(self.clean(json.loads(value)), ensure_ascii=False)
                except json.JSONDecodeError:
                    pass
            if value.startswith(("/Users/", "/home/", "/root/", "/mnt/", "/var/", "file://")):
                return ""
            return self.text(value)
        if isinstance(value, bytes):
            raise ValueError("数据库含未支持的二进制字段，需明确脱敏策略")
        return value

    def inspect_database(self, db):
        if db.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('view','trigger') OR upper(sql) LIKE '%CREATE VIRTUAL TABLE%' LIMIT 1"
        ).fetchone():
            raise ValueError("快照含视图、触发器或虚拟表，需要单独审阅")
        tables = [
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        for table in tables:
            columns = [row[1] for row in db.execute(f"PRAGMA table_info({quote(table)})")]
            if table not in self.schema or set(columns) - set(self.schema[table]):
                raise ValueError(f"未登记的数据结构：{table}；请审阅后扩展 extra_schema")
            for row in db.execute(f"SELECT * FROM {quote(table)}"):
                self.discover(dict(zip(columns, row)))
        return tables

    def database(self, path, tables):
        with sqlite3.connect(path) as db:
            db.execute("PRAGMA secure_delete=ON")
            # 只保留表/索引；触发器可能含外部路径、原文和有副作用的 SQL。
            for (name,) in db.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            ).fetchall():
                raise ValueError(f"快照含数据库触发器，需单独审阅：{name}")
            for table in tables:
                if table in EMPTY_TABLES:
                    db.execute(f"DELETE FROM {quote(table)}")
                    continue
                columns = [row[1] for row in db.execute(f"PRAGMA table_info({quote(table)})")]
                rows = db.execute(f"SELECT rowid, * FROM {quote(table)}").fetchall()
                for rowid, *row in rows:
                    values = [self.clean(value, key) for key, value in zip(columns, row)]
                    assignments = ",".join(f"{quote(key)}=?" for key in columns)
                    db.execute(
                        f"UPDATE {quote(table)} SET {assignments} WHERE rowid=?", [*values, rowid]
                    )
            db.commit()
            db.execute("VACUUM")
