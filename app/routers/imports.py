from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from ..db import connect
from ..importer import CHANNELS, import_csv


router = APIRouter()


@router.post("/api/import/{kind}")
async def upload(kind: str, request: Request, shop_id: int):
    if shop_id not in (1, 2): raise HTTPException(400, "请选择店铺")
    if kind not in CHANNELS: raise HTTPException(400, "未知渠道")
    filename = unquote(request.headers.get("x-filename", kind))
    if Path(filename).suffix.lower() != ".csv": raise HTTPException(400, "仅支持CSV文件")
    content = await request.body()
    if len(content) > 50 * 1024 * 1024: raise HTTPException(413, "文件超过50MB")
    try:
        return await run_in_threadpool(import_csv, shop_id, kind, filename, content)
    except (ValueError, UnicodeError) as error:
        raise HTTPException(400, str(error)) from error


@router.get("/api/imports")
def imports():
    with connect() as db:
        return [dict(row) for row in db.execute("""
          SELECT b.*,s.name shop_name FROM import_batches b JOIN shops s ON s.id=b.shop_id
          WHERE b.kind IN ('FBP','realFBS','WHD') ORDER BY b.id DESC LIMIT 10
        """)]
