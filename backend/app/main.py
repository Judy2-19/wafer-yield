from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import layout_store, store
from .data_source import get_dies, judge_wafer, list_item_names, list_wafers, test_mysql_connection
from .export_excel import build_judge_workbook
from .layout_tsv import LayoutParseError
from .specs import get_template, is_builtin_template, list_templates

store.init_db()

app = FastAPI(title="晶圆台良品率判定系统", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


class DbConfigIn(BaseModel):
    host: str = "127.0.0.1"
    port: int = 3306
    database: str = "mg_nano"
    user: str = "root"
    password: str = ""
    use_mock: bool = True


class SpecItem(BaseModel):
    name: str
    display_name: str | None = None
    condition: str | None = None
    lsl: float | None = None
    lsl_4v: float | None = None  # MPD Dark Current 4V 组 Min
    target: float | None = None
    usl: float | None = None
    usl_4v: float | None = None  # MPD Dark Current 4V 组 Max
    enabled: bool = True
    unit: str | None = None
    note: str | None = None
    custom: bool = False


class JudgeIn(BaseModel):
    wafer: str
    specs: list[SpecItem]
    user_name: str = "operator"
    start: str | None = None  # CreateTime 起（含）
    end: str | None = None  # CreateTime 止（含）


class TemplateIn(BaseModel):
    id: str
    name: str
    specs: list[SpecItem]
    user_name: str = "operator"


class SaveJudgeIn(BaseModel):
    wafer: str
    payload: dict[str, Any]


@app.get("/api/health")
async def health() -> dict[str, Any]:
    cfg = store.get_db_config() or {}
    return {
        "status": "ok",
        "use_mock": bool(cfg.get("use_mock", True)),
        "frontend_dist": (FRONTEND_DIST / "index.html").exists(),
    }


@app.get("/api/db/config")
async def api_get_db_config() -> dict[str, Any]:
    cfg = store.get_db_config() or {}
    # 不回传明文密码全文，仅提示是否已设置
    return {
        **{k: v for k, v in cfg.items() if k != "password"},
        "password_set": bool(cfg.get("password")),
        "password": "",
    }


@app.post("/api/db/config")
async def api_save_db_config(body: DbConfigIn) -> dict[str, Any]:
    current = store.get_db_config() or {}
    password = body.password
    if not password and current.get("password"):
        password = current["password"]
    store.save_db_config({**body.model_dump(), "password": password})
    store.add_audit("db_config_save", {"host": body.host, "database": body.database, "use_mock": body.use_mock})
    return {"ok": True}


@app.post("/api/db/force-mock")
async def api_force_mock() -> dict[str, Any]:
    """工程师机一键切回 Mock，避免误配 MySQL 导致整页无数据。"""
    cfg = store.get_db_config() or {}
    store.save_db_config(
        {
            "host": cfg.get("host") or "127.0.0.1",
            "port": int(cfg.get("port") or 3306),
            "database": cfg.get("database") or "mg_nano",
            "user": cfg.get("user") or "root",
            "password": cfg.get("password") or "",
            "use_mock": True,
        }
    )
    store.add_audit("db_force_mock", {})
    return {"ok": True, "message": "已切换为 Mock 模式", "use_mock": True}


@app.post("/api/db/test")
async def api_test_db(body: DbConfigIn) -> dict[str, Any]:
    try:
        return await test_mysql_connection(body.model_dump())
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


@app.get("/api/layout/current")
async def api_layout_current() -> dict[str, Any]:
    info = layout_store.public_layout_info()
    if info is None:
        return {"ok": False, "layout": None, "message": "尚未上传 Shot 布局文件"}
    return {"ok": True, "layout": info}


@app.post("/api/layout/upload")
async def api_layout_upload(file: UploadFile = File(...)) -> dict[str, Any]:
    name = file.filename or "layout.txt"
    if not re_search_layout_ext(name):
        raise HTTPException(status_code=400, detail="请上传 .txt 或 .tsv 布局文件")
    try:
        raw = await file.read()
        text = raw.decode("utf-8-sig")
        layout = layout_store.set_layout_from_text(text, filename=name)
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="文件编码需为 UTF-8") from exc
    except LayoutParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"布局解析失败: {exc}") from exc
    store.add_audit(
        "layout_upload",
        {
            "filename": name,
            "shot_count": len(layout.get("shots") or []),
            "site_count": len(layout.get("sites") or []),
            "layout_id": layout.get("layout_id"),
        },
    )
    return {"ok": True, "layout": layout_store.public_layout_info(layout)}


def re_search_layout_ext(name: str) -> bool:
    lower = name.lower()
    return lower.endswith(".txt") or lower.endswith(".tsv")


@app.get("/api/wafers")
async def api_wafers(start: str | None = None, end: str | None = None) -> dict[str, Any]:
    try:
        wafers = await list_wafers(start=start, end=end)
        return {"wafers": wafers}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/item-names")
async def api_item_names(wafer: str | None = None) -> dict[str, Any]:
    try:
        items = await list_item_names(wafer)
        return {"items": items}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/wafers/{wafer}/dies")
async def api_dies(
    wafer: str,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    try:
        dies = await get_dies(wafer, start=start, end=end)
        return {"wafer": wafer, "dies": dies}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/judge")
async def api_judge(body: JudgeIn) -> dict[str, Any]:
    try:
        result = await judge_wafer(
            body.wafer,
            [s.model_dump() for s in body.specs],
            start=body.start,
            end=body.end,
        )
        store.add_audit(
            "judge",
            {
                "wafer": body.wafer,
                "yield": result["stats"]["yield"],
                "die_total": result["stats"]["total"],
                "start": body.start,
                "end": body.end,
            },
            user_name=body.user_name,
        )
        return result
    except RuntimeError as exc:
        # 未上传布局等业务错误
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/judge/save")
async def api_save_judge(body: SaveJudgeIn) -> dict[str, Any]:
    store.save_judge_result(body.wafer, body.payload)
    store.add_audit("judge_save", {"wafer": body.wafer})
    return {"ok": True}


@app.get("/api/spec-templates")
async def api_list_templates() -> dict[str, Any]:
    # 默认内置模板始终保留在最前；用户模板追加其后（不可覆盖内置 id）
    builtin = list_templates()
    saved = [t for t in store.list_saved_templates() if not is_builtin_template(t["id"])]
    return {"templates": builtin + saved}


@app.get("/api/spec-templates/{template_id}")
async def api_get_template(template_id: str) -> dict[str, Any]:
    t = get_template(template_id)
    if t:
        return t
    saved = store.get_saved_template(template_id)
    if saved:
        return {**saved, "builtin": False}
    raise HTTPException(status_code=404, detail="模板不存在")


@app.post("/api/spec-templates")
async def api_save_template(body: TemplateIn) -> dict[str, Any]:
    if is_builtin_template(body.id):
        raise HTTPException(
            status_code=400,
            detail="默认模板不可覆盖，请使用「另存为新模板」保存客户标准",
        )
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="模板名称不能为空")
    store.save_template(body.id, body.name.strip(), [s.model_dump() for s in body.specs])
    store.add_audit(
        "spec_template_save",
        {"id": body.id, "name": body.name, "specs": [s.model_dump() for s in body.specs]},
        user_name=body.user_name,
    )
    return {"ok": True, "id": body.id, "name": body.name.strip()}


@app.delete("/api/spec-templates/{template_id}")
async def api_delete_template(template_id: str) -> dict[str, Any]:
    if is_builtin_template(template_id):
        raise HTTPException(status_code=400, detail="默认模板不可删除")
    ok = store.delete_template(template_id)
    if not ok:
        raise HTTPException(status_code=404, detail="模板不存在")
    store.add_audit("spec_template_delete", {"id": template_id})
    return {"ok": True}


@app.get("/api/audit-logs")
async def api_audit(limit: int = 100) -> dict[str, Any]:
    return {"logs": store.list_audit(limit)}


@app.post("/api/export/excel")
async def api_export_excel(payload: dict[str, Any]) -> Response:
    data = build_judge_workbook(payload)
    wafer = payload.get("wafer") or "wafer"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{wafer}_judge.xlsx"'},
    )


@app.get("/")
async def root_page() -> Any:
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return {
        "status": "ok",
        "message": "Backend API is running. Open frontend at http://127.0.0.1:5173/ or build frontend/dist for single-port mode.",
        "health": "/api/health",
        "docs": "/docs",
    }


# 单端口模式：后端同时托管前端构建产物
_assets = FRONTEND_DIST / "assets"
if _assets.is_dir():
    app.mount("/assets", StaticFiles(directory=_assets), name="frontend-assets")
