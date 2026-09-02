from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app import document_ingest, web_access


def run_probe(root: Path, query: str, download_url: str, *, max_results: int = 5) -> Dict[str, Any]:
    policy = web_access.BrowserPolicy(headless=True)
    with web_access.LocalBrowser(root, policy) as browser:
        search = browser.search(query, max_results=max_results)
        first = (search.get("results") or [])[0]
        page = browser.open_page(str(first.get("url") or ""), max_chars=20_000)
        download = browser.download(download_url)
    extracted = document_ingest.ingest_artifact(root, str(download.get("artifactId") or ""))
    artifacts = web_access.list_artifacts(root, limit=20)
    checks = {
        "browserAvailable": bool(web_access.status(root).get("available")),
        "searchResults": int(search.get("resultCount") or 0) > 0,
        "pageText": bool(str(page.get("text") or "").strip()),
        "pageChunks": bool(page.get("chunks")),
        "searchArtifact": bool(search.get("artifactPath")),
        "pageArtifact": bool(page.get("artifactPath")),
        "downloadHash": len(str(download.get("sha256") or "")) == 64,
        "downloadArtifact": bool(download.get("filePath")) and bool(download.get("manifestPath")),
        "downloadExtracted": int(extracted.get("chunkCount") or 0) > 0,
        "artifactIndex": int(artifacts.get("count") or 0) >= 3,
    }
    return {
        "schemaVersion": "parallm-web-access-probe/v1",
        "passed": all(checks.values()),
        "checks": checks,
        "query": query,
        "search": {
            "artifactId": search.get("artifactId"),
            "resultCount": search.get("resultCount"),
            "firstResult": first,
        },
        "page": {
            "artifactId": page.get("artifactId"),
            "title": page.get("title"),
            "url": page.get("finalUrl") or page.get("url"),
            "chars": page.get("chars"),
            "chunkCount": len(page.get("chunks") or []),
        },
        "download": {
            "artifactId": download.get("artifactId"),
            "url": download.get("finalUrl") or download.get("url"),
            "contentType": download.get("contentType"),
            "bytes": download.get("bytes"),
            "sha256": download.get("sha256"),
            "extractedChunks": extracted.get("chunkCount"),
        },
        "artifactCount": artifacts.get("count"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe ParaLLM's owned local-browser research path.")
    parser.add_argument("--query", default="Python 3.12 documentation", help="Public-web query used by the probe.")
    parser.add_argument(
        "--download-url",
        default="https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf",
        help="Small public document used to verify download and extraction.",
    )
    parser.add_argument("--max-results", type=int, default=5)
    parser.add_argument("--root", default="", help="Optional artifact root. Omit to use an isolated temporary root.")
    args = parser.parse_args()

    if args.root:
        result = run_probe(Path(args.root).resolve(), args.query, args.download_url, max_results=args.max_results)
    else:
        with tempfile.TemporaryDirectory(prefix="parallm-web-probe-") as directory:
            result = run_probe(Path(directory), args.query, args.download_url, max_results=args.max_results)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
