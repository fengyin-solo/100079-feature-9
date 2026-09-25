"""隧道设施业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "tunnel"
REQUIRED_FIELDS = ["隧道编码", "隧道名称", "隧道长度"]
# 修改时允许写入的字段；隧道状态由动作流转驱动，不允许直接改。
EDITABLE_FIELDS = [
    "隧道编码",
    "隧道名称",
    "隧道长度",
    "断面形式",
    "照明方式",
    "通风方式",
    "管养单位",
]
STATUS_ORDER = ["待移交", "正常养护", "检修封闭", "已停用"]
ACTION_RULES = {"办理移交": "正常养护", "安排检修": "检修封闭", "停用隧道": "已停用"}
NEGATIVE_ACTIONS = ["停用隧道"]

# 隧道长度合法区间（米）：前后端共用同一口径，前端常量见 tunnel/index.vue。
LENGTH_MIN_M = 0.1
LENGTH_MAX_M = 50000.0


def tunnel_length_issue(value: Any) -> str | None:
    """校验隧道长度，返回不可保存的原因；合法时返回 None。

    空值单独判定，便于把「旧记录缺失」与「填了非数字」区分成不同提示。
    """
    if value is None or not str(value).strip():
        return "隧道长度缺失，请填写长度"
    text = str(value).strip()
    try:
        number = float(text)
    except (TypeError, ValueError):
        return f"隧道长度必须是数字（米），当前填写「{text}」无法识别"
    if number != number or number in (float("inf"), float("-inf")):
        return f"隧道长度必须是数字（米），当前填写「{text}」无法识别"
    if number < LENGTH_MIN_M or number > LENGTH_MAX_M:
        return (
            f"隧道长度超出允许区间：{LENGTH_MIN_M:g}～{LENGTH_MAX_M:g} 米，"
            f"当前填写 {number:g} 米"
        )
    return None


def annotate_length(entry: dict[str, Any]) -> dict[str, Any]:
    """给单条记录补上长度完善情况，列表/明细/下拉都从这里取口径。"""
    issue = tunnel_length_issue(entry.get("隧道长度"))
    entry["lengthComplete"] = issue is None
    entry["lengthIssue"] = issue
    return entry


class TunnelService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("隧道编码", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        page_rows = [dict(row) for row in rows[start:start + size]]
        return [annotate_length(row) for row in page_rows], total

    def list_options(self) -> list[dict[str, Any]]:
        """关联下拉口径：长度待完善的记录照样返回，由前端标成「待完善」并禁用，不直接消失。"""
        return [
            annotate_length(dict(row))
            for row in store.rows(MODULE)
        ]

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return annotate_length(dict(entry)) if entry is not None else None

    def create_entry(
        self, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, list[str], str | None]:
        """返回 (记录, 缺失字段名, 长度不合法原因)；两类问题不会同时出现。"""
        missing = [
            field
            for field in REQUIRED_FIELDS
            if not str(values.get(field) or "").strip()
        ]
        if missing:
            return None, missing, None
        length_issue = tunnel_length_issue(values.get("隧道长度"))
        if length_issue is not None:
            return None, [], length_issue
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        # 长度统一按数值落库，避免「123 米」这类写法再次变成脏数据。
        entry["隧道长度"] = float(str(values["隧道长度"]).strip())
        for field in EDITABLE_FIELDS:
            if field not in entry:
                entry[field] = values.get(field)
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return annotate_length(dict(entry)), [], None

    def update_entry(
        self, entry_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        """修改隧道设施：必填缺失或长度不合法时整条不落地，并给出可读原因。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"隧道设施 {entry_id} 不存在或已归档"
        merged: dict[str, Any] = {field: entry.get(field) for field in EDITABLE_FIELDS}
        for field in EDITABLE_FIELDS:
            if field in values:
                merged[field] = values[field]
        missing = [
            field
            for field in REQUIRED_FIELDS
            if not str(merged.get(field) or "").strip()
        ]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        length_issue = tunnel_length_issue(merged.get("隧道长度"))
        if length_issue is not None:
            return None, length_issue
        for field in EDITABLE_FIELDS:
            entry[field] = merged[field]
        entry["隧道长度"] = float(str(merged["隧道长度"]).strip())
        return annotate_length(dict(entry)), "隧道设施已保存"

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"隧道设施 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于隧道设施可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return annotate_length(dict(entry)), f"隧道设施已{action}"
