"""隧道设施业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

import math
from typing import Any

from app.store import store

MODULE = "tunnel"
REQUIRED_FIELDS = ["隧道编码", "隧道名称", "隧道长度"]
OPTIONAL_FIELDS = ["断面形式", "照明方式", "通风方式", "管养单位"]
EDITABLE_FIELDS = REQUIRED_FIELDS + OPTIONAL_FIELDS
STATUS_ORDER = ["待移交", "正常养护", "检修封闭", "已停用"]
ACTION_RULES = {"办理移交": "正常养护", "安排检修": "检修封闭", "停用隧道": "已停用"}
NEGATIVE_ACTIONS = ["停用隧道"]

# 隧道长度以米计，登记与修改时必须落在该区间内。
LENGTH_MIN_M = 0.1
LENGTH_MAX_M = 50000.0


def parse_length(raw: Any) -> tuple[float | None, str | None]:
    """检查隧道长度，返回 (解析后的长度, 问题说明)。

    问题说明同时服务两类口径：
    - 登记/修改：有问题就拦下，不允许保存（缺失时给必填提示）；
    - 历史旧记录：缺失、非数字或超区间都算「待完善」异常数据，
      记录保留在列表与关联下拉里，只做标注，不直接消失。
    """
    if raw is None or not str(raw).strip():
        return None, "隧道长度缺失"
    # bool 在 Python 里是 int 的子类，JSON 的 true/false 不能当成长度。
    if isinstance(raw, bool):
        return None, f"隧道长度「{raw}」不是有效数字，需填写以米为单位的数值"
    if isinstance(raw, (int, float)):
        length = float(raw)
    else:
        text = str(raw).strip()
        try:
            length = float(text)
        except ValueError:
            return None, f"隧道长度「{text}」不是有效数字，需填写以米为单位的数值"
    if not math.isfinite(length):
        return None, "隧道长度不是有效数字，需填写以米为单位的数值"
    if length < LENGTH_MIN_M or length > LENGTH_MAX_M:
        return (
            None,
            f"隧道长度允许区间为 {LENGTH_MIN_M:g}～{LENGTH_MAX_M:g} 米，"
            f"当前填写 {length:g} 米，超出区间",
        )
    return length, None


def length_save_error(raw: Any) -> str | None:
    """登记/修改提交时的阻断原因；缺失单独给必填口径的提示。"""
    _length, problem = parse_length(raw)
    if problem is None:
        return None
    if problem == "隧道长度缺失":
        return "隧道长度为必填项，请填写数字长度（单位：米）"
    return problem


def annotate(row: dict[str, Any]) -> dict[str, Any]:
    """给记录补上「长度待完善」标记，状态完全由长度值推导，重进页面也不会丢。"""
    item = dict(row)
    _length, problem = parse_length(item.get("隧道长度"))
    item["长度待完善"] = problem is not None
    if problem:
        item["长度问题"] = problem
    else:
        item["长度问题"] = None
    return item


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
        page_rows = [annotate(row) for row in rows[start:start + size]]
        return page_rows, total

    def list_options(self) -> list[dict[str, Any]]:
        """养护对象等关联下拉使用：长度待完善的隧道照常返回，由调用方标注，不剔除。"""
        options: list[dict[str, Any]] = []
        for row in store.rows(MODULE):
            length, _problem = parse_length(row.get("隧道长度"))
            item = annotate(row)
            options.append({
                "id": item["id"],
                "隧道编码": item.get("隧道编码", ""),
                "隧道名称": item.get("隧道名称", ""),
                "隧道长度": length,
                "长度待完善": item["长度待完善"],
                "长度问题": item["长度问题"],
            })
        return options

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return annotate(entry) if entry is not None else None

    def _validate(self, values: dict[str, Any]) -> tuple[str | None, float | None]:
        missing = [
            field
            for field in ("隧道编码", "隧道名称")
            if not str(values.get(field) or "").strip()
        ]
        if missing:
            return f"缺少必填字段：{'、'.join(missing)}", None
        length, problem = parse_length(values.get("隧道长度"))
        if problem is not None:
            if problem == "隧道长度缺失":
                return "隧道长度为必填项，请填写数字长度（单位：米）", None
            return problem, None
        return None, length

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
        message, length = self._validate(values)
        if message is not None:
            return None, message
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        self._apply_fields(entry, values, length)
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return annotate(entry), None

    def update_entry(
        self, entry_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str | None]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"隧道设施 {entry_id} 不存在或已归档"
        merged = {field: entry.get(field, "") for field in EDITABLE_FIELDS}
        for field in EDITABLE_FIELDS:
            if field in values:
                merged[field] = values[field]
        message, length = self._validate(merged)
        if message is not None:
            return None, message
        self._apply_fields(entry, merged, length)
        return annotate(entry), None

    @staticmethod
    def _apply_fields(entry: dict[str, Any], values: dict[str, Any], length: float) -> None:
        for field in ("隧道编码", "隧道名称", *OPTIONAL_FIELDS):
            entry[field] = str(values.get(field) or "").strip()
        entry["隧道长度"] = length

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
        return entry, f"隧道设施已{action}"
