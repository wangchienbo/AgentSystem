"""系统级压缩下载路由

提供一个系统唯一的文件下载服务，随系统启动而启动。
支持：
  - POST /api/download/folder  — 压缩指定文件夹为 zip，返回下载链接
  - GET  /download/{filename}  — 实际文件下载端点
  - GET  /api/download/list    — 列出当前可用的下载文件
"""
from __future__ import annotations

import io
import logging
import os
import shutil
import tempfile
import time
import uuid
import zipfile
from datetime import datetime, timedelta, UTC
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.runtime_paths import resolve_runtime_paths

logger = logging.getLogger(__name__)

router = APIRouter()

# 下载文件存储目录
_runtime_paths = resolve_runtime_paths()
_DOWNLOAD_DIR = _runtime_paths.data_dir / "downloads"
_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 下载记录：filename → metadata
_download_registry: dict[str, dict] = {}

# 文件保留时长（默认 24 小时）
_DOWNLOAD_TTL_HOURS = 24


def _cleanup_expired():
    """清理过期下载文件"""
    now = datetime.now(UTC)
    expired = [
        name for name, meta in _download_registry.items()
        if datetime.fromisoformat(meta["expires_at"]) < now
    ]
    for name in expired:
        path = _DOWNLOAD_DIR / name
        if path.exists():
            path.unlink()
        del _download_registry[name]
    if expired:
        logger.info("Cleaned up %d expired download files", len(expired))


class FolderDownloadRequest(BaseModel):
    folder_path: str = Field(description="要压缩的文件夹绝对路径或相对于项目根目录的路径")
    label: str = Field(default="", description="下载文件标签（用于生成友好的文件名）")
    ttl_hours: int = Field(default=24, ge=1, le=168, description="文件保留时长（小时）")


@router.post("/api/download/folder")
async def download_folder(req: FolderDownloadRequest):
    """压缩指定文件夹为 zip，返回下载链接"""
    _cleanup_expired()

    folder = Path(req.folder_path)
    if not folder.exists():
        # 尝试相对项目根目录
        project_root = Path(__file__).resolve().parents[2]
        folder = project_root / req.folder_path
        if not folder.exists():
            raise HTTPException(status_code=404, detail=f"文件夹不存在: {req.folder_path}")

    if not folder.is_dir():
        raise HTTPException(status_code=400, detail=f"路径不是文件夹: {req.folder_path}")

    # 生成文件名
    label = req.label or folder.name
    safe_label = "".join(c for c in label if c.isalnum() or c in "._- ") or "download"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_id = uuid.uuid4().hex[:6]
    filename = f"{safe_label}_{timestamp}_{short_id}.zip"

    zip_path = _DOWNLOAD_DIR / filename

    # 压缩文件夹
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for item in folder.rglob("*"):
                if item.is_file():
                    arcname = str(item.relative_to(folder.parent))
                    zf.write(item, arcname)
        size_mb = zip_path.stat().st_size / (1024 * 1024)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"压缩失败: {str(e)}")

    expires_at = datetime.now(UTC) + timedelta(hours=req.ttl_hours)
    download_meta = {
        "filename": filename,
        "label": safe_label,
        "source_path": str(folder),
        "size_mb": round(size_mb, 2),
        "created_at": datetime.now(UTC).isoformat(),
        "expires_at": expires_at.isoformat(),
        "ttl_hours": req.ttl_hours,
    }
    _download_registry[filename] = download_meta

    # 下载链接（使用 /download/ 路径，与 FileResponse 路由一致）
    base_url = os.environ.get("AGENTSYSTEM_BASE_URL", "")
    download_url = f"{base_url}/download/{filename}"

    logger.info("Created download: %s (%.1f MB, expires %s)", filename, size_mb, expires_at.isoformat())

    return {
        "success": True,
        "download_url": download_url,
        "filename": filename,
        "size_mb": download_meta["size_mb"],
        "expires_at": download_meta["expires_at"],
    }


@router.get("/api/download/list")
async def list_downloads():
    """列出当前可用的下载文件"""
    _cleanup_expired()
    return {
        "success": True,
        "downloads": list(_download_registry.values()),
        "count": len(_download_registry),
    }


@router.get("/api/download/{filename}")
async def get_download_info(filename: str):
    """获取单个下载文件的元信息"""
    if filename not in _download_registry:
        raise HTTPException(status_code=404, detail="下载文件不存在或已过期")
    return {"success": True, "download": _download_registry[filename]}
