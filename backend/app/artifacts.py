from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import boto3  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency in some runtimes
    boto3 = None

try:
    from botocore.config import Config as BotoConfig  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency in some runtimes
    BotoConfig = None

from .config import deployment_topology


ARTIFACT_CATEGORIES = {
    "checkpoints",
    "outputs",
    "sessions",
    "exports",
    "failed_calls",
    "provider_calls",
    "handoffs",
    "node_transfers",
}
MAX_FILESYSTEM_ARTIFACT_PATH = 248
MAX_ARTIFACT_FILENAME = 96


def object_storage_enabled(root: Optional[Path] = None) -> bool:
    return deployment_topology(root).artifact_backend == "object_storage"


def _s3_client(root: Optional[Path] = None):
    if boto3 is None:
        raise RuntimeError("boto3 dependency is not installed.")
    topology = deployment_topology(root)
    if not topology.object_store_url or not topology.object_store_bucket:
        raise RuntimeError("Object storage is not configured.")
    return boto3.client(
        "s3",
        endpoint_url=topology.object_store_url,
        aws_access_key_id=topology.object_store_access_key,
        aws_secret_access_key=topology.object_store_secret_key,
        region_name=topology.object_store_region or "us-east-1",
        config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}) if BotoConfig is not None else None,
    )


def _bucket_name(root: Optional[Path] = None) -> str:
    topology = deployment_topology(root)
    if not topology.object_store_bucket:
        raise RuntimeError("LOOP_OBJECT_STORE_BUCKET is not configured.")
    return str(topology.object_store_bucket)


def _object_key(category: str, name: str) -> str:
    normalized_category = str(category or "").strip().lower()
    if normalized_category not in ARTIFACT_CATEGORIES:
        raise RuntimeError(f"Unsupported artifact category: {category}")
    safe_name = _safe_artifact_name(str(name or ""))
    if not safe_name.endswith(".json"):
        raise RuntimeError("Artifact names must end with .json")
    return f"{normalized_category}/{safe_name}"


def _safe_artifact_name(name: str) -> str:
    safe_name = Path(str(name or "")).name
    if not safe_name.endswith(".json"):
        raise RuntimeError("Artifact names must end with .json")
    return safe_name


def _compact_artifact_name(name: str, max_length: int) -> str:
    safe_name = _safe_artifact_name(name)
    max_length = max(24, int(max_length or MAX_ARTIFACT_FILENAME))
    if len(safe_name) <= max_length:
        return safe_name
    stem = safe_name[:-5]
    digest = hashlib.sha1(safe_name.encode("utf-8")).hexdigest()[:12]
    prefix_budget = max(8, max_length - len(digest) - len("--.json"))
    prefix = re.sub(r"[^A-Za-z0-9_.-]+", "-", stem).strip("-._")[:prefix_budget].strip("-._") or "artifact"
    return f"{prefix}-{digest}.json"


def _filesystem_artifact_name(target_dir: Path, name: str) -> str:
    safe_name = _safe_artifact_name(name)
    available = MAX_FILESYSTEM_ARTIFACT_PATH - len(str(target_dir.resolve())) - 1
    max_length = max(24, min(MAX_ARTIFACT_FILENAME, available))
    return _compact_artifact_name(safe_name, max_length)


def _ensure_bucket(root: Optional[Path] = None) -> None:
    client = _s3_client(root)
    bucket = _bucket_name(root)
    try:
        client.head_bucket(Bucket=bucket)
    except Exception:  # noqa: BLE001
        client.create_bucket(Bucket=bucket)


def write_json_artifact(root: Optional[Path], category: str, name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    requested_name = _safe_artifact_name(str(name or ""))
    if not object_storage_enabled(root):
        topology = deployment_topology(root)
        target_dir = topology.data_root / str(category).strip().lower()
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_name = _filesystem_artifact_name(target_dir, requested_name)
        target_path = target_dir / safe_name
        # Re-assert the parent directory immediately before write so freshly
        # initialized eval workspaces cannot trip over a missing category path.
        target_path.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps(payload, indent=2, ensure_ascii=False)
        target_path.write_text(body, encoding="utf-8")
        stat = target_path.stat()
        return {
            "name": safe_name,
            "category": str(category).strip().lower(),
            "size": stat.st_size,
            "modifiedAt": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat(),
            "requestedName": requested_name if requested_name != safe_name else None,
        }

    safe_name = _safe_artifact_name(requested_name)
    body = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
    _ensure_bucket(root)
    client = _s3_client(root)
    client.put_object(
        Bucket=_bucket_name(root),
        Key=_object_key(category, safe_name),
        Body=body,
        ContentType="application/json; charset=utf-8",
    )
    return {
        "name": safe_name,
        "category": str(category).strip().lower(),
        "size": len(body),
        "modifiedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "requestedName": requested_name if requested_name != safe_name else None,
    }


def read_json_artifact(root: Optional[Path], category: str, name: str) -> Optional[Dict[str, Any]]:
    requested_name = _safe_artifact_name(str(name or ""))
    if not object_storage_enabled(root):
        topology = deployment_topology(root)
        target_dir = topology.data_root / str(category).strip().lower()
        safe_name = _filesystem_artifact_name(target_dir, requested_name)
        target_path = target_dir / safe_name
        if not target_path.exists() and safe_name != requested_name:
            legacy_path = target_dir / requested_name
            if legacy_path.exists():
                target_path = legacy_path
        if not target_path.exists():
            return None
        raw = target_path.read_text(encoding="utf-8", errors="replace").lstrip("\ufeff")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    client = _s3_client(root)
    try:
        safe_name = _safe_artifact_name(requested_name)
        response = client.get_object(Bucket=_bucket_name(root), Key=_object_key(category, safe_name))
    except Exception:  # noqa: BLE001
        return None
    raw = response["Body"].read().decode("utf-8", errors="replace").lstrip("\ufeff")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def list_json_artifacts(root: Optional[Path], categories: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    categories = [str(value).strip().lower() for value in (categories or list(ARTIFACT_CATEGORIES)) if str(value).strip()]
    if not object_storage_enabled(root):
        topology = deployment_topology(root)
        entries: List[Dict[str, Any]] = []
        for category in categories:
            target_dir = topology.data_root / category
            if not target_dir.exists():
                continue
            for artifact_file in target_dir.glob("*.json"):
                stat = artifact_file.stat()
                entries.append(
                    {
                        "name": artifact_file.name,
                        "category": category,
                        "size": stat.st_size,
                        "modifiedAt": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat(),
                    }
                )
        entries.sort(key=lambda item: str(item.get("modifiedAt") or ""), reverse=True)
        return entries

    client = _s3_client(root)
    bucket = _bucket_name(root)
    entries: List[Dict[str, Any]] = []
    for category in categories:
        prefix = f"{category}/"
        continuation_token: Optional[str] = None
        while True:
            params: Dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
            if continuation_token:
                params["ContinuationToken"] = continuation_token
            response = client.list_objects_v2(**params)
            for item in response.get("Contents", []) or []:
                key = str(item.get("Key") or "")
                name = key[len(prefix) :] if key.startswith(prefix) else Path(key).name
                modified = item.get("LastModified")
                modified_text = (
                    modified.astimezone(timezone.utc).replace(microsecond=0).isoformat()
                    if hasattr(modified, "astimezone")
                    else datetime.now(timezone.utc).replace(microsecond=0).isoformat()
                )
                entries.append(
                    {
                        "name": name,
                        "category": category,
                        "size": int(item.get("Size") or 0),
                        "modifiedAt": modified_text,
                    }
                )
            if not response.get("IsTruncated"):
                break
            continuation_token = str(response.get("NextContinuationToken") or "").strip() or None
    entries.sort(key=lambda item: str(item.get("modifiedAt") or ""), reverse=True)
    return entries


def delete_json_artifact(root: Optional[Path], category: str, name: str) -> bool:
    requested_name = _safe_artifact_name(str(name or ""))
    if not object_storage_enabled(root):
        topology = deployment_topology(root)
        target_dir = topology.data_root / str(category).strip().lower()
        safe_name = _filesystem_artifact_name(target_dir, requested_name)
        target_path = target_dir / safe_name
        if not target_path.exists() and safe_name != requested_name:
            legacy_path = target_dir / requested_name
            if legacy_path.exists():
                target_path = legacy_path
        if not target_path.exists():
            return False
        target_path.unlink()
        return True

    client = _s3_client(root)
    try:
        safe_name = _safe_artifact_name(requested_name)
        client.delete_object(Bucket=_bucket_name(root), Key=_object_key(category, safe_name))
    except Exception:  # noqa: BLE001
        return False
    return True
