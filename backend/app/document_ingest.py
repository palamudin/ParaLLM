from __future__ import annotations

import csv
import hashlib
import io
import json
import mimetypes
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from xml.etree import ElementTree

from . import storage


SCHEMA_VERSION = "parallm-document-ingest/v1"
DEFAULT_MAX_CHARS = 1_000_000
DEFAULT_CHUNK_CHARS = 3_600
DEFAULT_CHUNK_OVERLAP = 240
TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".markdown",
    ".rst",
    ".log",
    ".csv",
    ".tsv",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".xml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".py",
    ".js",
    ".ts",
    ".css",
    ".sql",
}


class DocumentIngestError(RuntimeError):
    pass


class _VisibleHTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._blocked_depth = 0
        self._parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg", "template"}:
            self._blocked_depth += 1
        elif not self._blocked_depth and tag.lower() in {"p", "div", "section", "article", "li", "br", "h1", "h2", "h3", "h4", "tr"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg", "template"} and self._blocked_depth:
            self._blocked_depth -= 1
        elif not self._blocked_depth and tag.lower() in {"p", "div", "section", "article", "li", "h1", "h2", "h3", "h4", "tr"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._blocked_depth and data.strip():
            self._parts.append(data)

    def text(self) -> str:
        return normalize_text(" ".join(self._parts))


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_text(value: Any) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def research_root(root: Path | str) -> Path:
    return storage.project_paths(Path(root)).data / "research"


def download_root(root: Path | str) -> Path:
    return research_root(root) / "downloads"


def artifact_dir(root: Path | str, artifact_id: str) -> Path:
    safe_id = re.sub(r"[^a-zA-Z0-9_-]+", "", str(artifact_id or ""))
    if not safe_id or safe_id != str(artifact_id or ""):
        raise DocumentIngestError("Invalid research artifact id.")
    candidate = (download_root(root) / safe_id).resolve()
    base = download_root(root).resolve()
    if candidate.parent != base:
        raise DocumentIngestError("Research artifact path escaped the download store.")
    return candidate


def read_manifest(root: Path | str, artifact_id: str) -> Dict[str, Any]:
    path = artifact_dir(root, artifact_id) / "manifest.json"
    if not path.is_file():
        raise DocumentIngestError(f"Research artifact not found: {artifact_id}")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DocumentIngestError(f"Research artifact manifest is unreadable: {artifact_id}") from exc
    if not isinstance(parsed, dict):
        raise DocumentIngestError(f"Research artifact manifest is invalid: {artifact_id}")
    return parsed


def resolve_downloaded_file(root: Path | str, artifact_id: str) -> tuple[Path, Dict[str, Any]]:
    manifest = read_manifest(root, artifact_id)
    file_name = str(manifest.get("fileName") or "").strip()
    if not file_name or Path(file_name).name != file_name:
        raise DocumentIngestError("Research artifact manifest has an invalid file name.")
    path = (artifact_dir(root, artifact_id) / file_name).resolve()
    if path.parent != artifact_dir(root, artifact_id).resolve() or not path.is_file():
        raise DocumentIngestError("Downloaded research file is missing.")
    actual_hash = sha256_bytes(path.read_bytes())
    expected_hash = str(manifest.get("sha256") or "").strip().lower()
    if expected_hash and actual_hash != expected_hash:
        raise DocumentIngestError("Downloaded research file failed its SHA-256 integrity check.")
    return path, manifest


def _decode_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _xml_text(raw: bytes) -> str:
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError:
        return _decode_text(raw)
    return normalize_text(" ".join(item.strip() for item in root.itertext() if item and item.strip()))


def _natural_key(value: str) -> List[Any]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value)]


def _extract_docx(path: Path) -> List[Dict[str, Any]]:
    with zipfile.ZipFile(path) as archive:
        raw = archive.read("word/document.xml")
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        raise DocumentIngestError("DOCX document XML is invalid.") from exc
    paragraphs: List[str] = []
    for paragraph in root.iter():
        if paragraph.tag.endswith("}p"):
            text = normalize_text(" ".join(item.strip() for item in paragraph.itertext() if item and item.strip()))
            if text:
                paragraphs.append(text)
    return [{"locator": "document", "text": "\n\n".join(paragraphs)}]


def _extract_pptx(path: Path) -> List[Dict[str, Any]]:
    sections: List[Dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        slide_names = sorted(
            [name for name in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)],
            key=_natural_key,
        )
        for index, name in enumerate(slide_names, start=1):
            text = _xml_text(archive.read(name))
            if text:
                sections.append({"locator": f"slide:{index}", "text": text})
    return sections


def _extract_xlsx(path: Path) -> List[Dict[str, Any]]:
    sections: List[Dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        shared: List[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            try:
                shared_root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
                shared = [normalize_text(" ".join(item.itertext())) for item in shared_root if normalize_text(" ".join(item.itertext()))]
            except ElementTree.ParseError:
                shared = []
        sheet_names = sorted(
            [name for name in archive.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)],
            key=_natural_key,
        )
        for index, name in enumerate(sheet_names, start=1):
            try:
                sheet_root = ElementTree.fromstring(archive.read(name))
            except ElementTree.ParseError:
                continue
            values: List[str] = []
            for cell in sheet_root.iter():
                if not cell.tag.endswith("}c"):
                    continue
                cell_type = str(cell.attrib.get("t") or "")
                raw_value = next((node.text or "" for node in cell if node.tag.endswith("}v")), "")
                value = raw_value
                if cell_type == "s" and raw_value.isdigit() and int(raw_value) < len(shared):
                    value = shared[int(raw_value)]
                if value.strip():
                    values.append(value.strip())
            if values:
                sections.append({"locator": f"sheet:{index}", "text": "\n".join(values)})
    return sections


def _extract_epub(path: Path) -> List[Dict[str, Any]]:
    sections: List[Dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        names = sorted(
            [name for name in archive.namelist() if Path(name).suffix.lower() in {".html", ".htm", ".xhtml"}],
            key=_natural_key,
        )
        for name in names:
            parser = _VisibleHTMLText()
            parser.feed(_decode_text(archive.read(name)))
            text = parser.text()
            if text:
                sections.append({"locator": name, "text": text})
    return sections


def _extract_pdf(path: Path) -> List[Dict[str, Any]]:
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError as exc:
        raise DocumentIngestError("PDF ingestion requires pypdf.") from exc
    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        raise DocumentIngestError(f"PDF could not be opened: {exc}") from exc
    sections: List[Dict[str, Any]] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = normalize_text(page.extract_text() or "")
        except Exception:
            text = ""
        if text:
            sections.append({"locator": f"page:{index}", "text": text})
    return sections


def _extract_delimited(raw: bytes, delimiter: str) -> List[Dict[str, Any]]:
    text = _decode_text(raw)
    rows: List[str] = []
    for row in csv.reader(io.StringIO(text), delimiter=delimiter):
        rows.append(" | ".join(str(value).strip() for value in row))
    return [{"locator": "table", "text": normalize_text("\n".join(rows))}]


def extract_sections(path: Path, content_type: str = "") -> List[Dict[str, Any]]:
    suffix = path.suffix.lower()
    media_type = str(content_type or mimetypes.guess_type(path.name)[0] or "").split(";", 1)[0].strip().lower()
    if suffix == ".pdf" or media_type == "application/pdf":
        return _extract_pdf(path)
    if suffix == ".docx":
        return _extract_docx(path)
    if suffix == ".pptx":
        return _extract_pptx(path)
    if suffix == ".xlsx":
        return _extract_xlsx(path)
    if suffix == ".epub":
        return _extract_epub(path)

    raw = path.read_bytes()
    if suffix == ".csv":
        return _extract_delimited(raw, ",")
    if suffix == ".tsv":
        return _extract_delimited(raw, "\t")
    if suffix in {".html", ".htm", ".xhtml"} or media_type in {"text/html", "application/xhtml+xml"}:
        parser = _VisibleHTMLText()
        parser.feed(_decode_text(raw))
        return [{"locator": "document", "text": parser.text()}]
    if suffix == ".json" or media_type == "application/json":
        try:
            parsed = json.loads(_decode_text(raw))
            return [{"locator": "document", "text": json.dumps(parsed, ensure_ascii=False, indent=2)}]
        except json.JSONDecodeError:
            pass
    if suffix == ".xml" or media_type.endswith("+xml") or media_type in {"application/xml", "text/xml"}:
        return [{"locator": "document", "text": _xml_text(raw)}]
    if suffix in TEXT_SUFFIXES or media_type.startswith("text/"):
        return [{"locator": "document", "text": normalize_text(_decode_text(raw))}]
    if b"\x00" not in raw[:8192]:
        return [{"locator": "document", "text": normalize_text(_decode_text(raw))}]
    raise DocumentIngestError(f"Unsupported binary document type: {suffix or media_type or 'unknown'}")


def chunk_sections(
    sections: Iterable[Dict[str, Any]],
    *,
    source_hash: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> tuple[List[Dict[str, Any]], bool]:
    remaining = max(1, int(max_chars))
    size = max(800, int(chunk_chars))
    overlap = max(0, min(int(overlap), size // 3))
    chunks: List[Dict[str, Any]] = []
    truncated = False
    ordinal = 0
    for section in sections:
        locator = str(section.get("locator") or "document")
        text = normalize_text(section.get("text"))
        if not text:
            continue
        if len(text) > remaining:
            text = text[:remaining]
            truncated = True
        start = 0
        while start < len(text):
            end = min(len(text), start + size)
            if end < len(text):
                boundary = max(text.rfind("\n", start + size // 2, end), text.rfind(". ", start + size // 2, end))
                if boundary > start:
                    end = boundary + 1
            body = normalize_text(text[start:end])
            if body:
                ordinal += 1
                chunk_id = "chunk_" + hashlib.sha256(
                    f"{source_hash}\n{locator}\n{ordinal}\n{body}".encode("utf-8", errors="replace")
                ).hexdigest()[:20]
                chunks.append(
                    {
                        "id": chunk_id,
                        "ordinal": ordinal,
                        "locator": locator,
                        "text": body,
                        "chars": len(body),
                        "sha256": hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest(),
                    }
                )
            if end >= len(text):
                break
            start = max(start + 1, end - overlap)
        remaining -= len(text)
        if remaining <= 0:
            truncated = True
            break
    return chunks, truncated


def ingest_artifact(root: Path | str, artifact_id: str, *, max_chars: int = DEFAULT_MAX_CHARS) -> Dict[str, Any]:
    path, manifest = resolve_downloaded_file(root, artifact_id)
    sections = extract_sections(path, str(manifest.get("contentType") or ""))
    chunks, truncated = chunk_sections(
        sections,
        source_hash=str(manifest.get("sha256") or sha256_bytes(path.read_bytes())),
        max_chars=max_chars,
    )
    if not chunks:
        raise DocumentIngestError("No machine-readable text could be extracted from the downloaded document.")
    result = {
        "schemaVersion": SCHEMA_VERSION,
        "artifactId": artifact_id,
        "fileName": path.name,
        "sourceUrl": manifest.get("finalUrl") or manifest.get("url"),
        "contentType": manifest.get("contentType") or mimetypes.guess_type(path.name)[0],
        "sourceSha256": manifest.get("sha256"),
        "extractedAt": utc_now(),
        "sectionCount": len(sections),
        "chunkCount": len(chunks),
        "truncated": truncated,
        "chunks": chunks,
    }
    target = artifact_dir(root, artifact_id) / "extracted.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**result, "extractedPath": str(target.relative_to(storage.project_paths(Path(root)).root)).replace("\\", "/")}


def load_ingested_artifact(root: Path | str, artifact_id: str) -> Dict[str, Any]:
    target = artifact_dir(root, artifact_id) / "extracted.json"
    if not target.is_file():
        return ingest_artifact(root, artifact_id)
    try:
        parsed = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DocumentIngestError("Extracted research artifact is unreadable.") from exc
    if not isinstance(parsed, dict):
        raise DocumentIngestError("Extracted research artifact is invalid.")
    return parsed


def select_chunks(root: Path | str, artifact_id: str, chunk_ids: Iterable[str]) -> List[Dict[str, Any]]:
    extracted = load_ingested_artifact(root, artifact_id)
    wanted = {str(item).strip() for item in chunk_ids if str(item).strip()}
    return [
        dict(chunk)
        for chunk in (extracted.get("chunks") or [])
        if isinstance(chunk, dict) and str(chunk.get("id") or "") in wanted
    ]
