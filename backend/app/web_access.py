from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import mimetypes
import os
import re
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlsplit, urlunsplit

from . import document_ingest, knowledgebase, source_authority, storage


SCHEMA_VERSION = "parallm-web-access/v1"
DEFAULT_TIMEOUT_MS = 45_000
DEFAULT_MAX_PAGE_CHARS = 80_000
DEFAULT_MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
DOCUMENT_SUFFIXES = {".pdf", ".docx", ".pptx", ".xlsx", ".epub", ".csv", ".tsv", ".txt", ".md", ".json"}


class WebAccessError(RuntimeError):
    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.status_code = int(status_code)


@dataclass(frozen=True)
class BrowserPolicy:
    external_web_access: bool = True
    allowed_domains: tuple[str, ...] = ()
    allow_private_network: bool = False
    headless: bool = True
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    max_page_chars: int = DEFAULT_MAX_PAGE_CHARS
    max_download_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES
    channel: str = "msedge"


def utc_now() -> str:
    return knowledgebase.utc_now()


def compact(value: Any, limit: int = 600) -> str:
    return knowledgebase.compact(value, limit)


def normalize_domains(value: Any) -> tuple[str, ...]:
    raw = value if isinstance(value, list) else [value] if isinstance(value, str) else []
    domains: List[str] = []
    for item in raw:
        candidate = str(item or "").strip().lower()
        candidate = re.sub(r"^https?://", "", candidate).split("/", 1)[0].split(":", 1)[0].strip(".")
        if candidate and re.fullmatch(r"[a-z0-9.-]+", candidate) and candidate not in domains:
            domains.append(candidate)
    return tuple(domains[:32])


def policy_from_config(config: Optional[Dict[str, Any]] = None, *, allow_private_network: bool = False) -> BrowserPolicy:
    current = config if isinstance(config, dict) else {}
    channel = str(current.get("browserChannel") or os.environ.get("PARALLM_BROWSER_CHANNEL") or "msedge").strip() or "msedge"
    return BrowserPolicy(
        external_web_access=knowledgebase.coerce_bool(current.get("externalWebAccess"), True),
        allowed_domains=normalize_domains(current.get("domains")),
        allow_private_network=bool(allow_private_network),
        headless=knowledgebase.coerce_bool(current.get("headless"), True),
        timeout_ms=max(5_000, min(120_000, int(current.get("timeoutMs") or DEFAULT_TIMEOUT_MS))),
        max_page_chars=max(4_000, min(500_000, int(current.get("maxPageChars") or DEFAULT_MAX_PAGE_CHARS))),
        max_download_bytes=max(1_048_576, min(250 * 1024 * 1024, int(current.get("maxDownloadBytes") or DEFAULT_MAX_DOWNLOAD_BYTES))),
        channel=channel,
    )


def _domain_allowed(host: str, allowed_domains: Iterable[str]) -> bool:
    domains = tuple(allowed_domains)
    return not domains or any(host == domain or host.endswith("." + domain) for domain in domains)


def _address_is_public(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    return bool(address.is_global)


def assert_safe_url(url: Any, policy: BrowserPolicy, *, apply_domain_filter: bool = True) -> str:
    if not policy.external_web_access:
        raise WebAccessError("External web access is disabled for this run.", 403)
    candidate = str(url or "").strip()
    parsed = urlsplit(candidate)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise WebAccessError("Web tools only accept absolute HTTP or HTTPS URLs.", 400)
    if parsed.username or parsed.password:
        raise WebAccessError("Credential-bearing URLs are not accepted by web tools.", 400)
    host = parsed.hostname.lower().strip(".")
    if apply_domain_filter and not _domain_allowed(host, policy.allowed_domains):
        raise WebAccessError(f"Domain is outside the research allowlist: {host}", 403)
    if not policy.allow_private_network:
        try:
            addresses = {entry[4][0] for entry in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)}
        except socket.gaierror as exc:
            raise WebAccessError(f"Could not resolve web host: {host}", 502) from exc
        if not addresses or any(not _address_is_public(address) for address in addresses):
            raise WebAccessError("Private, loopback, link-local, and reserved network destinations are blocked.", 403)
    return urlunsplit((parsed.scheme.lower(), parsed.netloc, parsed.path or "/", parsed.query, ""))


def _safe_file_name(value: Any, fallback: str = "download.bin") -> str:
    candidate = unquote(str(value or "")).replace("\\", "/").rsplit("/", 1)[-1]
    candidate = re.sub(r"[^a-zA-Z0-9._ -]+", "_", candidate).strip(" .")
    if not candidate or candidate in {".", ".."}:
        candidate = fallback
    stem = Path(candidate).stem[:96] or "download"
    suffix = Path(candidate).suffix[:16]
    return stem + suffix


def _content_disposition_file_name(value: str) -> str:
    encoded = re.search(r"filename\*=UTF-8''([^;]+)", value or "", flags=re.IGNORECASE)
    if encoded:
        return unquote(encoded.group(1).strip().strip('"'))
    plain = re.search(r"filename=([^;]+)", value or "", flags=re.IGNORECASE)
    return plain.group(1).strip().strip('"') if plain else ""


def _unwrap_search_url(value: str) -> str:
    candidate = str(value or "").strip()
    parsed = urlsplit(candidate)
    if "duckduckgo.com" in (parsed.hostname or "") and parsed.path.startswith("/l/"):
        redirect = parse_qs(parsed.query).get("uddg", [])
        if redirect:
            return unquote(redirect[0])
    if (parsed.hostname or "").lower().endswith("bing.com") and parsed.path.startswith("/ck/a"):
        encoded_values = parse_qs(parsed.query).get("u", [])
        if encoded_values:
            encoded = str(encoded_values[0] or "")
            if encoded.startswith("a1"):
                encoded = encoded[2:]
            try:
                decoded = base64.urlsafe_b64decode(encoded + ("=" * (-len(encoded) % 4))).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                decoded = ""
            if urlsplit(decoded).scheme.lower() in {"http", "https"}:
                return decoded
    return candidate


def _artifact_relative(root: Path | str, path: Path) -> str:
    base = storage.project_paths(Path(root)).root
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


class LocalBrowser:
    def __init__(self, root: Path | str, policy: Optional[BrowserPolicy] = None) -> None:
        self.root = storage.project_paths(Path(root)).root
        self.policy = policy or BrowserPolicy()
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._host_safety_cache: Dict[str, bool] = {}

    def __enter__(self) -> "LocalBrowser":
        try:
            from playwright.sync_api import sync_playwright
        except ModuleNotFoundError as exc:
            raise WebAccessError("Local browsing requires the pinned playwright package.", 503) from exc
        try:
            self._playwright = sync_playwright().start()
            launch_kwargs: Dict[str, Any] = {"headless": self.policy.headless}
            if self.policy.channel:
                launch_kwargs["channel"] = self.policy.channel
            self._browser = self._playwright.chromium.launch(**launch_kwargs)
            self._context = self._browser.new_context(
                accept_downloads=True,
                viewport={"width": 1440, "height": 1000},
                user_agent="ParaLLM-Research/1.0 (+local operator browser)",
            )
            self._context.set_default_timeout(self.policy.timeout_ms)
            self._context.set_default_navigation_timeout(self.policy.timeout_ms)
            self._context.route("**/*", self._guard_route)
        except Exception as exc:
            self.close()
            raise WebAccessError(f"Local browser could not start: {exc}", 503) from exc
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def close(self) -> None:
        for item in (self._context, self._browser):
            if item is not None:
                try:
                    item.close()
                except Exception:
                    pass
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
        self._context = None
        self._browser = None
        self._playwright = None

    def _guard_route(self, route: Any) -> None:
        request_url = str(route.request.url or "")
        parsed = urlsplit(request_url)
        if parsed.scheme in {"about", "blob", "data"}:
            route.continue_()
            return
        host = str(parsed.hostname or "").lower()
        if not host:
            route.abort()
            return
        cached = self._host_safety_cache.get(host)
        if cached is None:
            try:
                relaxed = BrowserPolicy(
                    external_web_access=self.policy.external_web_access,
                    allow_private_network=self.policy.allow_private_network,
                    timeout_ms=self.policy.timeout_ms,
                )
                assert_safe_url(request_url, relaxed, apply_domain_filter=False)
                cached = True
            except WebAccessError:
                cached = False
            self._host_safety_cache[host] = cached
        if not cached:
            route.abort()
            return
        if route.request.resource_type in {"media", "font"}:
            route.abort()
            return
        route.continue_()

    def _new_page(self) -> Any:
        if self._context is None:
            raise WebAccessError("Local browser is not running.", 503)
        return self._context.new_page()

    def search(self, query: str, *, max_results: int = 8) -> Dict[str, Any]:
        normalized_query = compact(query, 500)
        if not normalized_query:
            raise WebAccessError("web_search requires a non-empty query.", 400)
        max_results = max(1, min(20, int(max_results or 8)))
        search_query = normalized_query
        if self.policy.allowed_domains:
            search_query += " " + " OR ".join(f"site:{domain}" for domain in self.policy.allowed_domains)
        search_url = "https://www.bing.com/search?q=" + quote_plus(search_query)
        assert_safe_url(search_url, BrowserPolicy(external_web_access=self.policy.external_web_access, allow_private_network=self.policy.allow_private_network), apply_domain_filter=False)
        page = self._new_page()
        try:
            page.goto(search_url, wait_until="domcontentloaded")
            rows = page.locator("li.b_algo")
            results: List[Dict[str, Any]] = []
            for index in range(min(rows.count(), max_results * 2)):
                row = rows.nth(index)
                anchor = row.locator("h2 a").first
                if not anchor.count():
                    continue
                title = compact(anchor.inner_text(), 240)
                url = _unwrap_search_url(str(anchor.get_attribute("href") or ""))
                snippet_node = row.locator(".b_caption p").first
                snippet = compact(snippet_node.inner_text() if snippet_node.count() else "", 520)
                try:
                    safe_url = assert_safe_url(url, self.policy)
                except WebAccessError:
                    continue
                if safe_url in {item["url"] for item in results}:
                    continue
                results.append(
                    {
                        "rank": len(results) + 1,
                        "title": title or safe_url,
                        "url": safe_url,
                        "snippet": snippet,
                        "sourceAuthority": source_authority.grade_source(safe_url),
                    }
                )
                if len(results) >= max_results:
                    break
            if not results:
                raise WebAccessError("Search completed but yielded no allowed results.", 502)
        except WebAccessError:
            raise
        except Exception as exc:
            raise WebAccessError(f"Local browser search failed: {exc}", 502) from exc
        finally:
            page.close()
        artifact_id = "search_" + hashlib.sha256(f"{normalized_query}\n{utc_now()}".encode("utf-8")).hexdigest()[:16]
        payload = {
            "schemaVersion": SCHEMA_VERSION,
            "artifactId": artifact_id,
            "kind": "search",
            "query": normalized_query,
            "searchEngine": "bing-local-browser",
            "searchedAt": utc_now(),
            "resultCount": len(results),
            "results": results,
        }
        target = document_ingest.research_root(self.root) / "searches" / f"{artifact_id}.json"
        _write_json(target, payload)
        return {**payload, "artifactPath": _artifact_relative(self.root, target)}

    def open_page(self, url: str, *, max_chars: Optional[int] = None) -> Dict[str, Any]:
        safe_url = assert_safe_url(url, self.policy)
        limit = max(2_000, min(self.policy.max_page_chars, int(max_chars or self.policy.max_page_chars)))
        page = self._new_page()
        try:
            response = page.goto(safe_url, wait_until="domcontentloaded")
            final_url = assert_safe_url(page.url, self.policy)
            content_type = str((response.headers.get("content-type") if response is not None else "") or "").split(";", 1)[0].lower()
            if content_type and content_type not in {"text/html", "application/xhtml+xml", "text/plain"} and not content_type.startswith("text/"):
                raise WebAccessError(f"URL is a downloadable document ({content_type}); use web_download.", 409)
            title = compact(page.title(), 300)
            body = page.locator("body")
            text = body.inner_text(timeout=self.policy.timeout_ms) if body.count() else ""
            text = document_ingest.normalize_text(text)
            if not text:
                raise WebAccessError("Page opened but yielded no rendered text.", 502)
            truncated = len(text) > limit
            text = text[:limit]
            link_rows = page.locator("a[href]")
            links: List[Dict[str, str]] = []
            for index in range(min(link_rows.count(), 80)):
                anchor = link_rows.nth(index)
                href = str(anchor.get_attribute("href") or "").strip()
                if not href:
                    continue
                absolute = urljoin(final_url, href)
                try:
                    absolute = assert_safe_url(absolute, self.policy)
                except WebAccessError:
                    continue
                if absolute in {item["url"] for item in links}:
                    continue
                links.append(
                    {
                        "text": compact(anchor.inner_text(), 160),
                        "url": absolute,
                        "sourceAuthority": source_authority.grade_source(absolute),
                    }
                )
                if len(links) >= 24:
                    break
        except WebAccessError:
            raise
        except Exception as exc:
            raise WebAccessError(f"Local browser could not open the page: {exc}", 502) from exc
        finally:
            page.close()
        page_hash = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
        artifact_id = "page_" + hashlib.sha256(f"{final_url}\n{page_hash}".encode("utf-8")).hexdigest()[:16]
        chunks, chunk_truncated = document_ingest.chunk_sections(
            [{"locator": "page", "text": text}],
            source_hash=page_hash,
            max_chars=limit,
        )
        payload = {
            "schemaVersion": SCHEMA_VERSION,
            "artifactId": artifact_id,
            "kind": "page",
            "url": safe_url,
            "finalUrl": final_url,
            "title": title or final_url,
            "contentType": content_type or "text/html",
            "openedAt": utc_now(),
            "sha256": page_hash,
            "chars": len(text),
            "truncated": bool(truncated or chunk_truncated),
            "text": text,
            "chunks": chunks,
            "links": links,
            "sourceAuthority": source_authority.grade_source(final_url),
        }
        target = document_ingest.research_root(self.root) / "pages" / f"{artifact_id}.json"
        _write_json(target, payload)
        return {**payload, "artifactPath": _artifact_relative(self.root, target)}

    def download(self, url: str, *, file_name: str = "") -> Dict[str, Any]:
        if self._context is None:
            raise WebAccessError("Local browser is not running.", 503)
        current_url = assert_safe_url(url, self.policy)
        response: Any = None
        for _ in range(6):
            try:
                response = self._context.request.get(current_url, timeout=self.policy.timeout_ms, fail_on_status_code=False, max_redirects=0)
            except Exception as exc:
                raise WebAccessError(f"Browser download request failed: {exc}", 502) from exc
            if response.status not in {301, 302, 303, 307, 308}:
                break
            location = str(response.headers.get("location") or "").strip()
            response.dispose()
            if not location:
                raise WebAccessError("Download redirect did not include a destination.", 502)
            current_url = assert_safe_url(urljoin(current_url, location), self.policy)
        if response is None:
            raise WebAccessError("Browser download did not receive a response.", 502)
        if response.status < 200 or response.status >= 300:
            status = int(response.status)
            response.dispose()
            raise WebAccessError(f"Download failed with HTTP {status}.", status if 400 <= status < 600 else 502)
        content_length = int(response.headers.get("content-length") or 0)
        if content_length > self.policy.max_download_bytes:
            response.dispose()
            raise WebAccessError("Download exceeds the configured size limit.", 413)
        raw = response.body()
        headers = dict(response.headers)
        response.dispose()
        if len(raw) > self.policy.max_download_bytes:
            raise WebAccessError("Download exceeds the configured size limit.", 413)
        digest = hashlib.sha256(raw).hexdigest()
        artifact_id = "download_" + digest[:16]
        disposition_name = _content_disposition_file_name(str(headers.get("content-disposition") or ""))
        inferred_name = file_name or disposition_name or Path(urlsplit(current_url).path).name or "download"
        content_type = str(headers.get("content-type") or "application/octet-stream").split(";", 1)[0].strip().lower()
        safe_name = _safe_file_name(inferred_name)
        if not Path(safe_name).suffix:
            guessed = mimetypes.guess_extension(content_type) or ".bin"
            safe_name += guessed
        target_dir = document_ingest.artifact_dir(self.root, artifact_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / safe_name
        target.write_bytes(raw)
        manifest = {
            "schemaVersion": SCHEMA_VERSION,
            "artifactId": artifact_id,
            "kind": "download",
            "url": str(url),
            "finalUrl": current_url,
            "fileName": safe_name,
            "contentType": content_type,
            "bytes": len(raw),
            "sha256": digest,
            "downloadedAt": utc_now(),
            "sourceAuthority": source_authority.grade_source(current_url),
        }
        manifest_path = target_dir / "manifest.json"
        _write_json(manifest_path, manifest)
        return {
            **manifest,
            "filePath": _artifact_relative(self.root, target),
            "manifestPath": _artifact_relative(self.root, manifest_path),
        }

    def research(
        self,
        query: str,
        *,
        max_results: int = 6,
        open_top: int = 3,
        download_documents: bool = True,
    ) -> Dict[str, Any]:
        search = self.search(query, max_results=max_results)
        opened: List[Dict[str, Any]] = []
        downloads: List[Dict[str, Any]] = []
        warnings: List[str] = []
        search_results = [item for item in (search.get("results") or []) if isinstance(item, dict)]
        admissible = [
            item
            for item in search_results
            if bool((item.get("sourceAuthority") or {}).get("evidenceEligible"))
        ]
        admissible.sort(key=source_authority.source_selection_key)
        rejected_sources = [
            {
                "rank": item.get("rank"),
                "title": item.get("title"),
                "url": item.get("url"),
                "sourceAuthority": item.get("sourceAuthority"),
                "reason": str((item.get("sourceAuthority") or {}).get("reason") or "Source is not evidence eligible."),
            }
            for item in search_results
            if not bool((item.get("sourceAuthority") or {}).get("evidenceEligible"))
        ]
        for result in admissible[: max(0, min(6, int(open_top or 0)))]:
            url = str((result or {}).get("url") or "")
            suffix = Path(urlsplit(url).path).suffix.lower()
            try:
                if download_documents and suffix in DOCUMENT_SUFFIXES:
                    download = self.download(url)
                    extracted = document_ingest.ingest_artifact(self.root, str(download["artifactId"]))
                    downloads.append({**download, "extracted": extracted})
                else:
                    opened.append(self.open_page(url))
            except WebAccessError as exc:
                if exc.status_code == 409 and download_documents:
                    try:
                        download = self.download(url)
                        extracted = document_ingest.ingest_artifact(self.root, str(download["artifactId"]))
                        downloads.append({**download, "extracted": extracted})
                        continue
                    except (WebAccessError, document_ingest.DocumentIngestError) as download_exc:
                        warnings.append(f"{url}: {download_exc}")
                        continue
                warnings.append(f"{url}: {exc}")
            except document_ingest.DocumentIngestError as exc:
                warnings.append(f"{url}: {exc}")
        artifact_id = "research_" + hashlib.sha256(
            f"{compact(query, 500)}\n{search.get('artifactId')}\n{utc_now()}".encode("utf-8")
        ).hexdigest()[:16]
        payload = {
            "schemaVersion": SCHEMA_VERSION,
            "artifactId": artifact_id,
            "kind": "research_packet",
            "query": compact(query, 500),
            "createdAt": utc_now(),
            "search": search,
            "pages": opened,
            "downloads": downloads,
            "rejectedSources": rejected_sources,
            "evidenceEligibleResultCount": len(admissible),
            "warnings": warnings[:20],
            "sourceUrls": list(
                dict.fromkeys(
                    [str(item.get("finalUrl") or item.get("url") or "") for item in [*opened, *downloads] if str(item.get("finalUrl") or item.get("url") or "")]
                )
            ),
        }
        target = document_ingest.research_root(self.root) / "packets" / f"{artifact_id}.json"
        _write_json(target, payload)
        return {**payload, "artifactPath": _artifact_relative(self.root, target)}


def list_artifacts(root: Path | str, *, limit: int = 100) -> Dict[str, Any]:
    base = document_ingest.research_root(root)
    rows: List[Dict[str, Any]] = []
    for path in base.rglob("*.json") if base.exists() else []:
        if path.name == "extracted.json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or not payload.get("artifactId"):
            continue
        rows.append(
            {
                "artifactId": payload.get("artifactId"),
                "kind": payload.get("kind"),
                "title": payload.get("title") or payload.get("fileName") or payload.get("query"),
                "url": payload.get("finalUrl") or payload.get("url"),
                "createdAt": payload.get("openedAt") or payload.get("downloadedAt") or payload.get("searchedAt") or payload.get("createdAt"),
                "path": _artifact_relative(root, path),
            }
        )
    rows.sort(key=lambda item: str(item.get("createdAt") or ""), reverse=True)
    return {"schemaVersion": SCHEMA_VERSION, "count": min(len(rows), limit), "artifacts": rows[: max(1, min(500, int(limit or 100)))]}


def load_page_artifact(root: Path | str, artifact_id: str) -> Dict[str, Any]:
    safe_id = re.sub(r"[^a-zA-Z0-9_-]+", "", str(artifact_id or ""))
    path = document_ingest.research_root(root) / "pages" / f"{safe_id}.json"
    if safe_id != artifact_id or not path.is_file():
        raise WebAccessError(f"Page artifact not found: {artifact_id}", 404)
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise WebAccessError("Page artifact is invalid.", 500)
    return parsed


def artifact_chunks(root: Path | str, artifact_id: str) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if str(artifact_id).startswith("download_"):
        artifact = document_ingest.load_ingested_artifact(root, artifact_id)
    elif str(artifact_id).startswith("page_"):
        artifact = load_page_artifact(root, artifact_id)
    else:
        raise WebAccessError("Memory retention accepts page or downloaded-document artifact ids.", 400)
    chunks = [dict(item) for item in (artifact.get("chunks") or []) if isinstance(item, dict) and item.get("id")]
    return artifact, chunks


def retain_artifact_chunks(
    root: Path | str,
    *,
    artifact_id: str,
    chunk_ids: Iterable[str],
    bank_id: str = "",
    rationale: str = "",
    tags: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    artifact, chunks = artifact_chunks(root, artifact_id)
    wanted = {str(item).strip() for item in chunk_ids if str(item).strip()}
    selected = [chunk for chunk in chunks if str(chunk.get("id") or "") in wanted]
    if not selected:
        raise WebAccessError("No valid source chunk ids were selected for memory retention.", 400)
    source_url = str(artifact.get("sourceUrl") or artifact.get("finalUrl") or artifact.get("url") or "")
    source_grade = source_authority.grade_source(source_url)
    if not bool(source_grade.get("memoryEligible")):
        raise WebAccessError(
            f"Source is not eligible for durable memory ({source_grade.get('sourceClass')}): {source_grade.get('caveat')}",
            403,
        )
    source_hash = str(artifact.get("sourceSha256") or artifact.get("sha256") or "")
    host = str(urlsplit(source_url).hostname or "").lower()
    merged_tags = ["web-research", "source-backed"]
    if host:
        merged_tags.append("source:" + knowledgebase.slug(host, "web"))
    for tag in tags or []:
        normalized = knowledgebase.slug(tag, "")
        if normalized and normalized not in merged_tags:
            merged_tags.append(normalized)
    items: List[Dict[str, Any]] = []
    for chunk in selected:
        chunk_id = str(chunk.get("id") or "")
        locator = str(chunk.get("locator") or "document")
        items.append(
            {
                "title": compact(artifact.get("title") or artifact.get("fileName") or source_url or artifact_id, 140),
                "content": str(chunk.get("text") or ""),
                "type": "artifact",
                "source": "web_document",
                "sourceId": f"{artifact_id}#{chunk_id}",
                "context": compact(f"Source: {source_url}. Locator: {locator}. Retention rationale: {rationale}", 1000),
                "tags": merged_tags,
                "metadata": {
                    "artifactId": artifact_id,
                    "chunkId": chunk_id,
                    "locator": locator,
                    "sourceUrl": source_url,
                    "sourceSha256": source_hash,
                    "acquiredAt": artifact.get("openedAt") or artifact.get("extractedAt") or artifact.get("downloadedAt"),
                    "retentionRationale": compact(rationale, 360),
                    "sourceAuthority": source_grade,
                },
            }
        )
    result = knowledgebase.retain(
        root,
        {
            "bankId": bank_id or knowledgebase.DEFAULT_BANK_ID,
            "source": "web_document",
            "items": items,
        },
    )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "artifactId": artifact_id,
        "requestedChunkIds": sorted(wanted),
        "acceptedChunkIds": [str(item.get("id")) for item in selected],
        "memory": result,
        "sourceImmutable": True,
        "sourceAuthority": source_grade,
    }


def status(root: Path | str) -> Dict[str, Any]:
    try:
        import playwright

        playwright_available = bool(playwright)
    except ModuleNotFoundError:
        playwright_available = False
    edge_path = Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
    return {
        "schemaVersion": SCHEMA_VERSION,
        "available": playwright_available and edge_path.is_file(),
        "playwrightAvailable": playwright_available,
        "browserChannel": "msedge",
        "browserPresent": edge_path.is_file(),
        "browserPath": str(edge_path) if edge_path.is_file() else None,
        "artifactStore": _artifact_relative(root, document_ingest.research_root(root)),
        "artifactSummary": list_artifacts(root, limit=20),
    }
