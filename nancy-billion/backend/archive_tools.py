"""Real file archiving/document/image utility tools -- zip/unzip, image
resize/convert, PDF merge/split. All real operations against real files on
disk (no simulated content), reusing already-installed deps (Pillow,
pypdf) rather than adding new ones for this batch.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from workspace_uri import resolve_oc_path

ARCHIVE_TOOLS = [
    {
        "name": "zip_files",
        "description": "Create a real .zip archive from one or more real files/folders on the user's computer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "paths": {"type": "array", "items": {"type": "string"}, "description": "Files and/or folders to include."},
                "output_path": {"type": "string", "description": "Where to save the .zip file."},
            },
            "required": ["paths", "output_path"],
        },
    },
    {
        "name": "unzip_file",
        "description": "Extract a real .zip archive to a real folder on the user's computer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "zip_path": {"type": "string"},
                "output_dir": {"type": "string", "description": "Folder to extract into (created if it doesn't exist)."},
            },
            "required": ["zip_path", "output_dir"],
        },
    },
    {
        "name": "resize_image",
        "description": "Resize and/or convert a real image file (e.g. shrink a huge photo, convert .png to .jpg).",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "output_path": {"type": "string"},
                "width": {"type": "integer"},
                "height": {"type": "integer", "description": "Omit to keep aspect ratio from width."},
            },
            "required": ["path", "output_path", "width"],
        },
    },
    {
        "name": "merge_pdfs",
        "description": "Merge two or more real PDF files into one, in the given order.",
        "input_schema": {
            "type": "object",
            "properties": {
                "paths": {"type": "array", "items": {"type": "string"}},
                "output_path": {"type": "string"},
            },
            "required": ["paths", "output_path"],
        },
    },
    {
        "name": "split_pdf",
        "description": "Extract a real page range from a real PDF into a new PDF file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "output_path": {"type": "string"},
                "start_page": {"type": "integer", "description": "1-indexed, inclusive."},
                "end_page": {"type": "integer", "description": "1-indexed, inclusive. Omit for just start_page."},
            },
            "required": ["path", "output_path", "start_page"],
        },
    },
]


def zip_files(paths: List[str], output_path: str) -> Dict[str, Any]:
    out = Path(resolve_oc_path(output_path)).expanduser()
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for raw in paths:
                p = Path(resolve_oc_path(raw)).expanduser()
                if not p.exists():
                    return {"success": False, "error": f"No such path: {raw}"}
                if p.is_file():
                    zf.write(p, arcname=p.name)
                else:
                    for child in p.rglob("*"):
                        if child.is_file():
                            zf.write(child, arcname=str(child.relative_to(p.parent)))
        return {"success": True, "output_path": str(out), "size_bytes": out.stat().st_size}
    except Exception as e:
        return {"success": False, "error": str(e)}


def unzip_file(zip_path: str, output_dir: str) -> Dict[str, Any]:
    zp = Path(resolve_oc_path(zip_path)).expanduser()
    out_dir = Path(resolve_oc_path(output_dir)).expanduser()
    if not zp.is_file():
        return {"success": False, "error": f"No such file: {zip_path}"}
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zp) as zf:
            names = zf.namelist()
            zf.extractall(out_dir)
        return {"success": True, "output_dir": str(out_dir), "extracted_files": len(names)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def resize_image(path: str, output_path: str, width: int, height: Optional[int] = None) -> Dict[str, Any]:
    p = Path(resolve_oc_path(path)).expanduser()
    out = Path(resolve_oc_path(output_path)).expanduser()
    if not p.is_file():
        return {"success": False, "error": f"No such file: {path}"}
    try:
        from PIL import Image
        img = Image.open(p)
        if height is None:
            ratio = width / img.width
            height = round(img.height * ratio)
        resized = img.resize((width, height))
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.suffix.lower() in (".jpg", ".jpeg") and resized.mode in ("RGBA", "P"):
            resized = resized.convert("RGB")
        resized.save(out)
        return {"success": True, "output_path": str(out), "width": width, "height": height}
    except Exception as e:
        return {"success": False, "error": str(e)}


def merge_pdfs(paths: List[str], output_path: str) -> Dict[str, Any]:
    out = Path(resolve_oc_path(output_path)).expanduser()
    try:
        from pypdf import PdfWriter
        writer = PdfWriter()
        for raw in paths:
            p = Path(resolve_oc_path(raw)).expanduser()
            if not p.is_file():
                return {"success": False, "error": f"No such file: {raw}"}
            writer.append(str(p))
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "wb") as f:
            writer.write(f)
        return {"success": True, "output_path": str(out), "page_count": len(writer.pages)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def split_pdf(path: str, output_path: str, start_page: int, end_page: Optional[int] = None) -> Dict[str, Any]:
    p = Path(resolve_oc_path(path)).expanduser()
    out = Path(resolve_oc_path(output_path)).expanduser()
    if not p.is_file():
        return {"success": False, "error": f"No such file: {path}"}
    end_page = end_page or start_page
    try:
        from pypdf import PdfReader, PdfWriter
        reader = PdfReader(str(p))
        total = len(reader.pages)
        if start_page < 1 or end_page > total or start_page > end_page:
            return {"success": False, "error": f"Invalid page range {start_page}-{end_page} for a {total}-page PDF."}
        writer = PdfWriter()
        for i in range(start_page - 1, end_page):
            writer.add_page(reader.pages[i])
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "wb") as f:
            writer.write(f)
        return {"success": True, "output_path": str(out), "pages_extracted": end_page - start_page + 1}
    except Exception as e:
        return {"success": False, "error": str(e)}
