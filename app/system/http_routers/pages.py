"""静态页面与资源服务域路由（favicon / studio / debug-log / download / root / workbench / login 页）。

从 http_test_server.py 拆出（原 424-485 行静态页 + login 页面部分）。
依赖通过 deps 持有器获取。
"""
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from app.system.http_routers.deps import get_static_dir, get_templates


def create_pages_router() -> APIRouter:
    router = APIRouter()
    templates = get_templates()
    static_dir = get_static_dir()

    @router.get("/favicon.ico")
    async def favicon():
        from fastapi.responses import Response
        return Response(content=b"", media_type="image/x-icon")

    @router.get("/studio", response_class=HTMLResponse)
    async def novel_studio_page():
        studio_path = Path(__file__).resolve().parent.parent / "novel_studio" / "templates" / "studio.html"
        if studio_path.exists():
            from fastapi.responses import HTMLResponse as _HTML
            content = studio_path.read_text(encoding="utf-8")
            return _HTML(
                content=content,
                headers={"Cache-Control": "no-cache, no-store, must-revalidate, max-age=0"}
            )
        return HTMLResponse("<html><body><h1>Novel Studio</h1><p>Template not found</p></body></html>")

    @router.get("/debug-log")
    async def debug_log(msg: str = "", ts: str = ""):
        """Client-side debug logging endpoint"""
        import logging
        logging.getLogger("app.system.http_test_server").info("[CLIENT] %s (ts=%s)", msg, ts)
        return HTMLResponse("ok")

    @router.get("/download/{filename:path}")
    async def download_file(filename: str):
        """静态文件下载"""
        safe = Path(filename).name  # 防止路径穿越
        file_path = static_dir / safe
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(file_path, filename=safe, media_type="application/octet-stream")

    @router.get("/", response_class=FileResponse)
    async def root():
        # Ensure the index.html exists; if not, fall back to a minimal placeholder
        index_path = static_dir / "index.html"
        if not index_path.is_file():
            # Create a simple placeholder page on-the-fly
            placeholder = """<html><head><title>AgentSystem</title></head><body><h1>AgentSystem 已启动</h1><p>请检查 static/index.html 是否存在。</p></body></html>"""
            return HTMLResponse(content=placeholder, status_code=200)
        return FileResponse(index_path)

    @router.get("/workbench", response_class=FileResponse)
    async def workbench():
        """新时代 AI 操作系统统一工作台（App 桌面 + Skill 库 + 自由设计 + Shell）。"""
        wb_path = static_dir / "workbench.html"
        if not wb_path.is_file():
            return HTMLResponse(content="<h1>workbench.html 未找到</h1>", status_code=404)
        return FileResponse(wb_path)

    @router.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"title": "Login - AgentSystem"},
        )

    return router
