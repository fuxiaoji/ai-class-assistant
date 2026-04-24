"""
REST API 路由
提供会话配置管理、文件上传等接口
"""
import uuid
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

from ..models.schemas import SessionConfig, SessionConfigResponse, UploadResponse
from ..services.session_service import session_manager
from ..services.material_service import material_service
from ..core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.get("/health")
async def health_check():
    """健康检查接口"""
    return {"status": "ok", "message": "AI 听课助手后端运行中"}


@router.post("/session/new")
async def create_session():
    """创建新会话，返回 session_id"""
    session_id = str(uuid.uuid4())[:8]
    session_manager.create(session_id)
    return {"session_id": session_id}


@router.get("/session/{session_id}/config", response_model=SessionConfigResponse)
async def get_session_config(session_id: str):
    """获取会话配置"""
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    return SessionConfigResponse(
        session_id=session_id,
        system_prompt=session.system_prompt,
        course_name=session.course_name,
        course_materials_preview=session.course_materials[:200] if session.course_materials else "",
        is_listening=session.is_listening,
    )


@router.put("/session/{session_id}/config")
async def update_session_config(session_id: str, config: SessionConfig):
    """更新会话配置（系统提示词、课程名称、课件内容）"""
    session = session_manager.get_or_create(session_id)
    session.system_prompt = config.system_prompt
    session.course_name = config.course_name
    session.course_materials = config.course_materials
    return {"message": "配置已更新", "session_id": session_id}


@router.post("/session/{session_id}/upload-material", response_model=UploadResponse)
async def upload_material(session_id: str, file: UploadFile = File(...)):
    """
    上传课件文件（PDF/TXT/MD/DOCX）
    自动提取文本并存入会话的课件内容
    """
    max_size = settings.max_file_size_mb * 1024 * 1024
    content = await file.read()

    if len(content) > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大，最大支持 {settings.max_file_size_mb}MB"
        )

    allowed_types = {".pdf", ".txt", ".md", ".docx"}
    import os
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed_types:
        raise HTTPException(
            status_code=415,
            detail=f"不支持的文件格式，支持：{', '.join(allowed_types)}"
        )

    # 保存文件
    file_path = await material_service.save_file(file.filename or "upload", content)

    # 提取文本
    extracted_text = material_service.extract_text(file_path)
    truncated_text = material_service.truncate_text(extracted_text)

    # 更新会话课件内容（追加）
    session = session_manager.get_or_create(session_id)
    if session.course_materials:
        session.course_materials += f"\n\n---\n\n{truncated_text}"
    else:
        session.course_materials = truncated_text

    return UploadResponse(
        filename=file.filename or "upload",
        extracted_text_length=len(extracted_text),
        preview=extracted_text[:200],
    )


@router.delete("/session/{session_id}/material")
async def clear_material(session_id: str):
    """清空课件内容"""
    session = session_manager.get(session_id)
    if session:
        session.course_materials = ""
    return {"message": "课件内容已清空"}


@router.get("/session/{session_id}/transcript")
async def get_transcript(session_id: str):
    """获取完整识别文本历史"""
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {
        "session_id": session_id,
        "transcript": session.full_transcript,
        "total": len(session.full_transcript),
    }


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """删除会话"""
    session_manager.delete(session_id)
    return {"message": "会话已删除"}
