from datetime import datetime

from fastapi import APIRouter, HTTPException, Request

from ..db import connect, transaction
from ..dingtalk import configured as dingtalk_configured, next_push_time
from .common import read_bounded_json


router = APIRouter()
JSON_MAX_BODY_BYTES = 64 * 1024


def _dingtalk_settings():
    with connect() as db:
        row = dict(db.execute("SELECT * FROM notification_settings WHERE id=1").fetchone())
        last = db.execute("""SELECT stats_date,status,attempted_at,sent_at,error FROM notification_runs
          WHERE kind='daily' ORDER BY attempted_at DESC LIMIT 1""").fetchone()
    row["daily_enabled"] = bool(row["daily_enabled"])
    row["weekdays"] = [int(value) for value in row["weekdays"].split(",") if value]
    row["configured"] = dingtalk_configured()
    row["last_run"] = dict(last) if last else None
    row["next_push_at"] = next_push_time(row)
    row.pop("template", None)
    return row


@router.get("/api/dingtalk/settings")
def dingtalk_settings():
    return _dingtalk_settings()


@router.put("/api/dingtalk/settings")
async def update_dingtalk_settings(request: Request):
    body = await read_bounded_json(request, JSON_MAX_BODY_BYTES, "钉钉设置")
    updates, args = [], []
    schedule_keys = {"daily_enabled", "push_time", "weekdays"}
    if schedule_keys & body.keys():
        if not schedule_keys <= body.keys():
            raise HTTPException(400, "请完整提交汇总开关、时间和星期")
        push_time = str(body.get("push_time", "")).strip()
        try:
            push_time = datetime.strptime(push_time, "%H:%M").strftime("%H:%M")
            weekdays = sorted({int(value) for value in body.get("weekdays", [])})
        except (TypeError, ValueError) as error:
            raise HTTPException(400, "钉钉推送时间或星期无效") from error
        if any(value not in range(1, 8) for value in weekdays):
            raise HTTPException(400, "钉钉推送星期无效")
        enabled = bool(body.get("daily_enabled"))
        if enabled and not weekdays:
            raise HTTPException(400, "启用昨日汇总时至少选择一天")
        updates.extend(("daily_enabled=?", "push_time=?", "weekdays=?"))
        args.extend((int(enabled), push_time, ",".join(map(str, weekdays))))
    if not updates:
        raise HTTPException(400, "没有可保存的设置")
    with transaction() as db:
        db.execute(f"UPDATE notification_settings SET {','.join(updates)} WHERE id=1", args)
    return _dingtalk_settings()
