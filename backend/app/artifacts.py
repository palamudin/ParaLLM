from __future__ import annotations

import json
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


ARTIFACT_CATEGORIES = {"checkpoints", "outputs", "sessions", "exports"}


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
    safe_name = Path(str(name or "")).name
    if not safe_name.endswith(".json"):
        raise RuntimeError("Artifact names must end with .json")
    return f"{normalized_category}/{safe_name}"


def _ensure_bucket(root: Optional[Path] = None) -> None:
    client = _s3_client(root)
    bucket = _bucket_name(root)
    try:
        client.head_bucket(Bucket=bucket)
    except Exception:  # noqa: BLE001
        client.create_bucket(Bucket=bucket)


def write_json_artifact(root: Optional[Path], category: str, name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    safe_name = Path(str(name or "")).name
    if not object_storage_enabled(root):
        topology = deployment_topology(root)
        target_dir = topology.data_root / str(category).strip().lower()
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / safe_name
        body = json.dumps(payload, indent=2, ensure_ascii=False)
        target_path.write_text(body, encoding="utf-8")
        stat = target_path.stat()
        return {
            "name": safe_name,
            "category": str(category).strip().lower(),
            "size": stat.st_size,
            "modifiedAt": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat(),
        }

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
    }


def read_json_artifact(root: Optional[Path], category: str, name: str) -> Optional[Dict[str, Any]]:
    safe_name = Path(str(name or "")).name
    if not object_storage_enabled(root):
        topology = deployment_topology(root)
        target_path = topology.data_root / str(category).strip().lower() / safe_name
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
    safe_name = Path(str(name or "")).name
    if not object_storage_enabled(root):
        topology = deployment_topology(root)
        target_path = topology.data_root / str(category).strip().lower() / safe_name
        if not target_path.exists():
            return False
        target_path.unlink()
        return True

    client = _s3_client(root)
    try:
        client.delete_object(Bucket=_bucket_name(root), Key=_object_key(category, safe_name))
    except Exception:  # noqa: BLE001
        return False
    return True
