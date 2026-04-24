"""
课件管理服务
支持上传和解析 PDF、TXT、MD 格式的课件文件
"""
import os
import logging
import aiofiles
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class MaterialService:
    """课件文件管理与文本提取服务"""

    def __init__(self, upload_dir: str = "./uploads"):
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    async def save_file(self, filename: str, content: bytes) -> str:
        """保存上传的文件，返回文件路径"""
        safe_name = Path(filename).name
        file_path = self.upload_dir / safe_name

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)

        logger.info(f"文件已保存: {file_path}")
        return str(file_path)

    def extract_text(self, file_path: str) -> str:
        """
        从文件中提取纯文本内容

        支持格式：PDF, TXT, MD, DOCX
        """
        path = Path(file_path)
        suffix = path.suffix.lower()

        try:
            if suffix == ".pdf":
                return self._extract_pdf(file_path)
            elif suffix in (".txt", ".md"):
                return self._extract_text_file(file_path)
            elif suffix == ".docx":
                return self._extract_docx(file_path)
            else:
                logger.warning(f"不支持的文件格式: {suffix}")
                return ""
        except Exception as e:
            logger.error(f"文本提取失败 {file_path}: {e}")
            return ""

    def _extract_pdf(self, file_path: str) -> str:
        """提取 PDF 文本"""
        try:
            import PyPDF2
            text_parts = []
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
            return "\n\n".join(text_parts)
        except ImportError:
            logger.error("PyPDF2 未安装")
            return ""

    def _extract_text_file(self, file_path: str) -> str:
        """提取纯文本文件"""
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    def _extract_docx(self, file_path: str) -> str:
        """提取 Word 文档文本"""
        try:
            from docx import Document
            doc = Document(file_path)
            return "\n".join(para.text for para in doc.paragraphs if para.text.strip())
        except ImportError:
            logger.error("python-docx 未安装")
            return ""

    def truncate_text(self, text: str, max_chars: int = 8000) -> str:
        """截断文本以适应 LLM 上下文窗口"""
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "\n\n[...内容已截断，显示前 8000 字...]"


material_service = MaterialService()
