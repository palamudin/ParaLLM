from __future__ import annotations

import ast
import bisect
import fnmatch
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


EXTENSIONS: Dict[str, str] = {
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".html": "HTML",
    ".py": "Python",
    ".ps1": "PowerShell",
    ".psm1": "PowerShell",
    ".cs": "C#",
    ".java": "Java",
    ".go": "Go",
    ".php": "PHP",
    ".rb": "Ruby",
    ".c": "C",
    ".cc": "C++",
    ".cpp": "C++",
    ".h": "C/C++",
    ".hpp": "C++",
}

SKIP_PATH_PARTS = {
    ".cache",
    ".codex",
    ".git",
    ".hg",
    ".idea",
    ".mypy_cache",
    ".next",
    ".nuxt",
    ".pytest_cache",
    ".qa",
    ".ruff_cache",
    ".svn",
    ".venv",
    ".vscode",
    "__pycache__",
    "bin",
    "build",
    "coverage",
    "dist",
    "logs",
    "node_modules",
    "obj",
    "old_logs",
    "packages",
    "playwright-report",
    "qa",
    "target",
    "temp",
    "test-results",
    "tmp",
    "vendor",
    "venv",
}

KEYWORDS = {
    "async",
    "await",
    "bool",
    "break",
    "case",
    "catch",
    "class",
    "console",
    "continue",
    "def",
    "dict",
    "do",
    "else",
    "except",
    "export",
    "filter",
    "finally",
    "float",
    "for",
    "foreach",
    "function",
    "if",
    "import",
    "int",
    "len",
    "list",
    "lock",
    "log",
    "main",
    "map",
    "new",
    "open",
    "print",
    "range",
    "read",
    "reduce",
    "require",
    "return",
    "setinterval",
    "settimeout",
    "sizeof",
    "str",
    "super",
    "switch",
    "then",
    "throw",
    "try",
    "typeof",
    "using",
    "while",
    "write",
}


@dataclass
class SourceFile:
    path: str
    absolute_path: Path
    ext: str
    lang: str
    size: int
    text: str
    clean: str
    line_starts: List[int]


@dataclass
class FunctionRecord:
    id: str
    name: str
    normalized: str
    type: str
    file: str
    ext: str
    lang: str
    line: int
    signature: str
    calls: Counter[str] = field(default_factory=Counter)
    external_calls: Counter[str] = field(default_factory=Counter)
    ambiguous_calls: Counter[str] = field(default_factory=Counter)
    callers: set[str] = field(default_factory=set)
    callees: set[str] = field(default_factory=set)

    @property
    def degree(self) -> int:
        return len(self.callers) + len(self.callees)


@dataclass(frozen=True)
class GitIgnoreRule:
    pattern: str
    negated: bool = False
    directory_only: bool = False
    anchored: bool = False
    basename_only: bool = False


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_path(path: Path | str) -> str:
    return str(path).replace("\\", "/").lstrip("./")


def normalize_name(name: Any) -> str:
    return str(name or "").lower().replace("_", "").replace("-", "").replace("$", "")


def line_starts(text: str) -> List[int]:
    starts = [0]
    for index, char in enumerate(text):
        if char == "\n":
            starts.append(index + 1)
    return starts


def line_number(starts: List[int], index: int) -> int:
    return max(1, bisect.bisect_right(starts, max(0, index)))


def get_original_line(text: str, index: int) -> str:
    start = text.rfind("\n", 0, max(0, index)) + 1
    end = text.find("\n", max(0, index))
    if end < 0:
        end = len(text)
    return text[start:end].strip()


def leading_spaces(line: str) -> int:
    return len(re.match(r"^\s*", line or "").group(0).replace("\t", "    "))


def get_ext(path: Path | str) -> str:
    return Path(str(path)).suffix.lower()


def path_is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def parse_gitignore_line(raw_line: str) -> Optional[GitIgnoreRule]:
    line = raw_line.rstrip("\n\r")
    if not line.strip():
        return None
    line = line.rstrip()
    if line.startswith("#"):
        return None
    negated = line.startswith("!")
    if negated:
        line = line[1:]
    if line.startswith("\\#") or line.startswith("\\!"):
        line = line[1:]
    line = line.strip()
    if not line:
        return None
    anchored = line.startswith("/")
    if anchored:
        line = line.lstrip("/")
    directory_only = line.endswith("/")
    pattern = normalize_path(line).rstrip("/")
    if not pattern:
        return None
    return GitIgnoreRule(
        pattern=pattern,
        negated=negated,
        directory_only=directory_only,
        anchored=anchored,
        basename_only="/" not in pattern,
    )


def load_gitignore_rules(root: Path) -> List[GitIgnoreRule]:
    gitignore = root / ".gitignore"
    if not gitignore.is_file():
        return []
    try:
        lines = gitignore.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [rule for line in lines if (rule := parse_gitignore_line(line))]


def match_gitignore_rule(rule: GitIgnoreRule, relative_path: str, *, is_dir: bool) -> bool:
    relative = normalize_path(relative_path).rstrip("/")
    if not relative:
        return False
    parts = [part for part in relative.split("/") if part]
    basename = parts[-1] if parts else relative
    pattern = rule.pattern

    if rule.directory_only:
        if rule.basename_only:
            return any(fnmatch.fnmatchcase(part, pattern) for part in parts)
        return relative == pattern or relative.startswith(f"{pattern}/")

    if rule.basename_only:
        return fnmatch.fnmatchcase(basename, pattern)
    if rule.anchored:
        return fnmatch.fnmatchcase(relative, pattern)
    return fnmatch.fnmatchcase(relative, pattern) or fnmatch.fnmatchcase(f"/{relative}", f"*/{pattern}")


def is_gitignored(relative_path: str, rules: List[GitIgnoreRule], *, is_dir: bool) -> bool:
    ignored = False
    for rule in rules:
        if match_gitignore_rule(rule, relative_path, is_dir=is_dir):
            ignored = not rule.negated
    return ignored


def should_skip_path(relative_path: str, ignore_rules: Optional[List[GitIgnoreRule]] = None, *, is_dir: bool = False) -> bool:
    parts = [part for part in normalize_path(relative_path).split("/") if part]
    if any(part in SKIP_PATH_PARTS for part in parts):
        return True
    return is_gitignored(relative_path, ignore_rules or [], is_dir=is_dir)


def has_skipped_path_part(relative_path: str) -> bool:
    parts = [part for part in normalize_path(relative_path).split("/") if part]
    return any(part in SKIP_PATH_PARTS for part in parts)


def strip_dead_text(src: str, ext: str) -> str:
    out = list(src)
    state = "code"
    quote = ""
    escape = False
    hash_comments = ext in {".py", ".rb", ".ps1", ".psm1"}
    index = 0
    while index < len(src):
        char = src[index]
        next_char = src[index + 1] if index + 1 < len(src) else ""
        if state == "line":
            if char == "\n":
                state = "code"
            else:
                out[index] = " "
            index += 1
            continue
        if state == "block":
            if char == "*" and next_char == "/":
                out[index] = " "
                out[index + 1] = " "
                index += 2
                state = "code"
                continue
            if char != "\n":
                out[index] = " "
            index += 1
            continue
        if state == "string":
            if char != "\n":
                out[index] = " "
            if escape:
                escape = False
                index += 1
                continue
            if char == "\\":
                escape = True
                index += 1
                continue
            if char == quote:
                state = "code"
                quote = ""
            index += 1
            continue
        if char == "/" and next_char == "/":
            out[index] = " "
            out[index + 1] = " "
            index += 2
            state = "line"
            continue
        if char == "/" and next_char == "*":
            out[index] = " "
            out[index + 1] = " "
            index += 2
            state = "block"
            continue
        if hash_comments and char == "#":
            out[index] = " "
            index += 1
            state = "line"
            continue
        if char in {"'", '"', "`"}:
            out[index] = " "
            quote = char
            escape = False
            state = "string"
        index += 1
    return "".join(out)


def find_matching_brace(text: str, start_index: int) -> int:
    depth = 0
    for index in range(start_index, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    return len(text)


def source_files(
    root: Path,
    *,
    max_file_bytes: int,
    max_files: int,
    relative_root: Optional[Path] = None,
    ignore_root: Optional[Path] = None,
) -> tuple[List[SourceFile], Dict[str, Any]]:
    root = root.resolve()
    relative_root = (relative_root or root).resolve()
    ignore_root = (ignore_root or relative_root).resolve()
    ignore_rules = load_gitignore_rules(ignore_root)
    files: List[SourceFile] = []
    skipped_by_ext = 0
    skipped_by_path = 0
    skipped_by_gitignore = 0
    skipped_large = 0
    read_errors = 0
    for current, dirs, filenames in os.walk(root):
        current_path = Path(current)
        kept_dirs = []
        for dirname in sorted(dirs):
            dir_path = current_path / dirname
            try:
                relative_dir = normalize_path(dir_path.relative_to(relative_root))
            except ValueError:
                relative_dir = normalize_path(dir_path.relative_to(root))
            if has_skipped_path_part(relative_dir):
                skipped_by_path += 1
                continue
            if is_gitignored(relative_dir, ignore_rules, is_dir=True):
                skipped_by_gitignore += 1
                continue
            kept_dirs.append(dirname)
        dirs[:] = kept_dirs

        for filename in sorted(filenames):
            if len(files) >= max_files:
                break
            path = current_path / filename
            if not path.is_file():
                continue
            try:
                relative = normalize_path(path.relative_to(relative_root))
            except ValueError:
                relative = normalize_path(path.relative_to(root))
            if has_skipped_path_part(relative):
                skipped_by_path += 1
                continue
            if is_gitignored(relative, ignore_rules, is_dir=False):
                skipped_by_gitignore += 1
                continue
            if should_skip_path(relative, ignore_rules, is_dir=False):
                skipped_by_path += 1
                continue
            ext = get_ext(path)
            lang = EXTENSIONS.get(ext)
            if not lang:
                skipped_by_ext += 1
                continue
            try:
                size = path.stat().st_size
            except OSError:
                read_errors += 1
                continue
            if size > max_file_bytes:
                skipped_large += 1
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                read_errors += 1
                continue
            files.append(
                SourceFile(
                    path=relative,
                    absolute_path=path,
                    ext=ext,
                    lang=lang,
                    size=size,
                    text=text,
                    clean=strip_dead_text(text, ext),
                    line_starts=line_starts(text),
                )
            )
            if len(files) >= max_files:
                break
        if len(files) >= max_files:
            break
    return files, {
        "skippedByExtension": skipped_by_ext,
        "skippedByPath": skipped_by_path,
        "skippedByGitIgnore": skipped_by_gitignore,
        "gitIgnoreRulesLoaded": len(ignore_rules),
        "skippedLarge": skipped_large,
        "readErrors": read_errors,
        "maxFilesHit": len(files) >= max_files,
    }


def resolve_scan_root(repo_root: Path | str, requested_root: str | None = None) -> Path:
    resolved_repo = Path(repo_root).resolve()
    requested = str(requested_root or ".").strip().replace("\\", "/")
    if requested in {"", "."}:
        return resolved_repo
    candidate = (resolved_repo / requested).resolve()
    if not path_is_within(candidate, resolved_repo):
        raise ValueError("Repo scan root must stay inside the repository.")
    if not candidate.exists() or not candidate.is_dir():
        raise ValueError("Repo scan root must be an existing folder.")
    return candidate


def discover_scan_roots(repo_root: Path | str, *, max_depth: int = 2) -> Dict[str, Any]:
    resolved_repo = Path(repo_root).resolve()
    ignore_rules = load_gitignore_rules(resolved_repo)
    roots: List[Dict[str, Any]] = [
        {"label": "Repository root", "value": ".", "path": ".", "depth": 0},
    ]
    queue: List[tuple[Path, int]] = [(resolved_repo, 0)]
    seen = {resolved_repo}
    while queue:
        current, depth = queue.pop(0)
        if depth >= max_depth:
            continue
        try:
            children = sorted([child for child in current.iterdir() if child.is_dir()], key=lambda item: item.name.lower())
        except OSError:
            continue
        for child in children:
            if child in seen:
                continue
            seen.add(child)
            relative = normalize_path(child.relative_to(resolved_repo))
            if has_skipped_path_part(relative) or is_gitignored(relative, ignore_rules, is_dir=True):
                continue
            sample, _meta = source_files(
                child,
                max_file_bytes=900_000,
                max_files=1,
                relative_root=resolved_repo,
                ignore_root=resolved_repo,
            )
            if sample:
                roots.append(
                    {
                        "label": relative,
                        "value": relative,
                        "path": relative,
                        "depth": depth + 1,
                    }
                )
                queue.append((child, depth + 1))
    return {
        "root": str(resolved_repo),
        "roots": roots,
        "scanPolicy": {
            "gitIgnoreRulesLoaded": len(ignore_rules),
            "skippedPathParts": sorted(SKIP_PATH_PARTS),
        },
    }


def make_function(file: SourceFile, name: str, kind: str, start: int, signature: str) -> FunctionRecord:
    line = line_number(file.line_starts, start)
    return FunctionRecord(
        id=f"{file.path}::{name}::{line}",
        name=name,
        normalized=normalize_name(name),
        type=kind,
        file=file.path,
        ext=file.ext,
        lang=file.lang,
        line=line,
        signature=signature.strip()[:500] or name,
    )


class _CallVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.calls: Counter[str] = Counter()
        self.external_calls: Counter[str] = Counter()
        self._depth = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        if self._depth > 0:
            return
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self.visit_FunctionDef(node)  # type: ignore[arg-type]

    def visit_Lambda(self, node: ast.Lambda) -> None:  # noqa: N802
        if self._depth > 0:
            return
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        if isinstance(node.func, ast.Name):
            name = node.func.id
            normalized = normalize_name(name)
            if name and normalized and normalized not in KEYWORDS:
                self.calls[name] += 1
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
            normalized = normalize_name(name)
            if name and normalized and normalized not in KEYWORDS:
                self.external_calls[name] += 1
        self.generic_visit(node)


def python_call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def parse_python(file: SourceFile) -> List[FunctionRecord]:
    try:
        tree = ast.parse(file.text)
    except SyntaxError:
        return parse_python_fallback(file)
    records: List[FunctionRecord] = []
    lines = file.text.splitlines()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        name = str(node.name)
        normalized = normalize_name(name)
        if not name or not normalized or normalized in KEYWORDS:
            continue
        line = max(1, int(getattr(node, "lineno", 1) or 1))
        start = file.line_starts[line - 1] if line - 1 < len(file.line_starts) else 0
        signature = lines[line - 1].strip() if line - 1 < len(lines) else name
        record = make_function(file, name, "python-def", start, signature)
        visitor = _CallVisitor()
        visitor.visit(node)
        visitor.calls.pop(name, None)
        visitor.calls.pop(record.normalized, None)
        record.calls = visitor.calls
        record.external_calls = visitor.external_calls
        records.append(record)
    return dedupe_functions(records)


def parse_python_fallback(file: SourceFile) -> List[FunctionRecord]:
    records: List[FunctionRecord] = []
    offset = 0
    for line in file.text.splitlines(True):
        match = re.match(r"^(\s*)(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(", line)
        if match:
            name = match.group(2)
            records.append(make_function(file, name, "python-def", offset + match.start(2), line))
        offset += len(line)
    return records


def collect_braced_matches(records: List[FunctionRecord], file: SourceFile, clean: str, pattern: re.Pattern[str], kind: str) -> None:
    for match in pattern.finditer(clean):
        name = match.group(1)
        normalized = normalize_name(name)
        if not name or not normalized or normalized in KEYWORDS:
            continue
        full = match.group(0)
        brace_offset = full.rfind("{")
        if brace_offset < 0:
            continue
        brace_index = match.start() + brace_offset
        end = find_matching_brace(clean, brace_index)
        start = match.start() + full.find(name)
        record = make_function(file, name, kind, start, get_original_line(file.text, start))
        record.calls = extract_text_calls(clean[brace_index + 1 : max(brace_index + 1, end - 1)], file.ext, record.normalized)
        records.append(record)


def parse_js_like(file: SourceFile, text: Optional[str] = None, offset: int = 0) -> List[FunctionRecord]:
    source = file.clean if text is None else strip_dead_text(text, ".js")
    records: List[FunctionRecord] = []
    patterns = [
        ("function", re.compile(r"\b(?:export\s+default\s+|export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{")),
        ("function-expression", re.compile(r"\b(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?function(?:\s+[A-Za-z_$][\w$]*)?\s*\([^)]*\)\s*\{")),
        ("arrow", re.compile(r"\b(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>\s*\{")),
        ("method", re.compile(r"(?:^|[\n\r])\s*(?:async\s+|static\s+|get\s+|set\s+)*([A-Za-z_$][\w$]*)\s*\([^\n\r;{}=]*\)\s*\{")),
    ]
    for kind, pattern in patterns:
        for match in pattern.finditer(source):
            name = match.group(1)
            normalized = normalize_name(name)
            if not name or not normalized or normalized in KEYWORDS:
                continue
            full = match.group(0)
            brace_offset = full.rfind("{")
            if brace_offset < 0:
                continue
            local_brace = match.start() + brace_offset
            local_end = find_matching_brace(source, local_brace)
            start = offset + match.start() + full.find(name)
            record = make_function(file, name, kind, start, get_original_line(file.text, start))
            body = source[local_brace + 1 : max(local_brace + 1, local_end - 1)]
            record.calls = extract_text_calls(body, file.ext, record.normalized)
            records.append(record)
    return dedupe_functions(records)


def parse_html(file: SourceFile) -> List[FunctionRecord]:
    records: List[FunctionRecord] = []
    for match in re.finditer(r"<script\b[^>]*>(.*?)</script>", file.text, flags=re.IGNORECASE | re.DOTALL):
        records.extend(parse_js_like(file, match.group(1), offset=match.start(1)))
    return dedupe_functions(records)


def parse_c_style(file: SourceFile) -> List[FunctionRecord]:
    records: List[FunctionRecord] = []
    patterns = [
        ("method", re.compile(r"\b(?:public|private|protected|internal|static|virtual|override|async|sealed|extern|partial|final|synchronized|native|inline|constexpr|friend|\s)+[A-Za-z_][\w:<>,\[\].?*&\s]+\s+([A-Za-z_~][\w]*)\s*\([^;{}]*\)\s*(?:const\s*)?(?:noexcept\s*)?(?:where\s+[^{}]+)?\{")),
        ("function", re.compile(r"\b(?:[A-Za-z_][\w:<>,\[\].?*&]+\s+)+([A-Za-z_~][\w]*)\s*\([^;{}]*\)\s*(?:const\s*)?(?:noexcept\s*)?\{")),
    ]
    for kind, pattern in patterns:
        collect_braced_matches(records, file, file.clean, pattern, kind)
    return dedupe_functions(records)


def parse_go(file: SourceFile) -> List[FunctionRecord]:
    records: List[FunctionRecord] = []
    pattern = re.compile(r"\bfunc\s+(?:\([^)]+\)\s*)?([A-Za-z_]\w*)\s*\([^)]*\)\s*(?:\([^)]*\)|[A-Za-z_][\w*\[\].]*)?\s*\{")
    collect_braced_matches(records, file, file.clean, pattern, "go-func")
    return dedupe_functions(records)


def parse_php(file: SourceFile) -> List[FunctionRecord]:
    records: List[FunctionRecord] = []
    collect_braced_matches(records, file, file.clean, re.compile(r"\bfunction\s+([A-Za-z_]\w*)\s*\([^)]*\)\s*\{"), "php-function")
    return dedupe_functions(records)


def parse_powershell(file: SourceFile) -> List[FunctionRecord]:
    records: List[FunctionRecord] = []
    collect_braced_matches(records, file, file.clean, re.compile(r"\bfunction\s+([A-Za-z_][\w:-]*)\s*(?:\([^)]*\))?\s*\{", re.IGNORECASE), "powershell-function")
    return dedupe_functions(records)


def parse_ruby(file: SourceFile) -> List[FunctionRecord]:
    records: List[FunctionRecord] = []
    offset = 0
    for line in file.text.splitlines(True):
        match = re.match(r"^(\s*)def\s+(?:self\.)?([A-Za-z_]\w*[!?=]?)\b", line)
        if match:
            name = match.group(2)
            records.append(make_function(file, name, "ruby-def", offset + match.start(2), line))
        offset += len(line)
    return dedupe_functions(records)


def parse_file(file: SourceFile) -> List[FunctionRecord]:
    if file.ext == ".py":
        return parse_python(file)
    if file.ext == ".html":
        return parse_html(file)
    if file.ext in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
        return parse_js_like(file)
    if file.ext in {".ps1", ".psm1"}:
        return parse_powershell(file)
    if file.ext == ".go":
        return parse_go(file)
    if file.ext == ".php":
        return parse_php(file)
    if file.ext == ".rb":
        return parse_ruby(file)
    return parse_c_style(file)


def extract_text_calls(body: str, ext: str, current_normalized: str) -> Counter[str]:
    calls: Counter[str] = Counter()
    for match in re.finditer(r"\b([A-Za-z_$][\w$]*|[A-Za-z_][A-Za-z0-9_-]*)\s*\(", body):
        name = match.group(1)
        normalized = normalize_name(name)
        if not name or not normalized or normalized in KEYWORDS or normalized == current_normalized:
            continue
        before_index = match.start() - 1
        while before_index >= 0 and body[before_index].isspace():
            before_index -= 1
        if before_index >= 0 and body[before_index] in {".", ":"}:
            continue
        before = body[max(0, match.start() - 22) : match.start()].strip()
        if re.search(r"\b(function|def|class|if|for|while|switch|catch|foreach)\s*$", before, flags=re.IGNORECASE):
            continue
        calls[name] += 1
    if ext in {".ps1", ".psm1"}:
        for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*-[A-Za-z0-9_-]+)\b", body):
            name = match.group(1)
            normalized = normalize_name(name)
            if name and normalized != current_normalized:
                calls[name] += 1
    return calls


def dedupe_functions(records: Iterable[FunctionRecord]) -> List[FunctionRecord]:
    seen: Dict[str, FunctionRecord] = {}
    for record in records:
        key = f"{record.file}|{record.name}|{record.line}"
        existing = seen.get(key)
        if existing is None or len(record.calls) > len(existing.calls):
            seen[key] = record
    return sorted(seen.values(), key=lambda item: (item.file, item.line, item.name))


def build_edges(functions: List[FunctionRecord], *, include_ambiguous: bool, ambiguous_target_limit: int) -> List[Dict[str, Any]]:
    by_name: Dict[str, List[FunctionRecord]] = defaultdict(list)
    for record in functions:
        by_name[record.normalized].append(record)

    edges: Dict[str, Dict[str, Any]] = {}
    for record in functions:
        for call_name, count in record.calls.items():
            normalized = normalize_name(call_name)
            candidates = [candidate for candidate in by_name.get(normalized, []) if candidate.id != record.id]
            if not candidates:
                record.external_calls[call_name] += count
                continue
            same_file = [candidate for candidate in candidates if candidate.file == record.file]
            targets = same_file
            ambiguous = False
            if not targets and len(candidates) == 1:
                targets = candidates
            elif not targets and include_ambiguous:
                targets = candidates[:ambiguous_target_limit]
                ambiguous = True
            elif not targets:
                record.ambiguous_calls[call_name] += count
                continue
            for target in targets:
                key = f"{record.id}=>{target.id}"
                edge = edges.setdefault(
                    key,
                    {
                        "sourceId": record.id,
                        "targetId": target.id,
                        "weight": 0,
                        "callNames": set(),
                        "ambiguous": ambiguous or len(candidates) > 1,
                    },
                )
                edge["weight"] += int(count)
                edge["callNames"].add(call_name)
                record.callees.add(target.id)
                target.callers.add(record.id)
    output: List[Dict[str, Any]] = []
    for edge in edges.values():
        output.append(
            {
                "sourceId": edge["sourceId"],
                "targetId": edge["targetId"],
                "weight": int(edge["weight"]),
                "callNames": sorted(edge["callNames"]),
                "ambiguous": bool(edge["ambiguous"]),
            }
        )
    output.sort(key=lambda item: (-int(item.get("weight") or 0), str(item.get("sourceId") or ""), str(item.get("targetId") or "")))
    return output


def module_key(path: str) -> str:
    parts = [part for part in normalize_path(path).split("/") if part]
    if len(parts) >= 2 and parts[0] in {"backend", "runtime", "scripts", "assets", "data", "deploy", ".agents"}:
        return "/".join(parts[:2])
    return parts[0] if parts else "."


def file_summary(files: List[SourceFile], functions: List[FunctionRecord]) -> List[Dict[str, Any]]:
    by_file: Dict[str, List[FunctionRecord]] = defaultdict(list)
    for record in functions:
        by_file[record.file].append(record)
    summaries = []
    for file in files:
        records = by_file.get(file.path, [])
        outbound = sum(len(record.callees) for record in records)
        inbound = sum(len(record.callers) for record in records)
        summaries.append(
            {
                "path": file.path,
                "lang": file.lang,
                "size": file.size,
                "functionCount": len(records),
                "outboundInternalEdges": outbound,
                "inboundInternalEdges": inbound,
                "module": module_key(file.path),
            }
        )
    summaries.sort(key=lambda item: (-int(item["functionCount"]), item["path"]))
    return summaries


def build_ai_readout(functions: List[FunctionRecord], edges: List[Dict[str, Any]], files: List[Dict[str, Any]], scan_meta: Dict[str, Any]) -> Dict[str, Any]:
    hotspots = sorted(functions, key=lambda item: (-item.degree, -len(item.callers), item.file, item.line))[:20]
    ambiguous_counter: Counter[str] = Counter()
    external_counter: Counter[str] = Counter()
    for record in functions:
        ambiguous_counter.update(record.ambiguous_calls)
        external_counter.update(record.external_calls)

    module_stats: Dict[str, Dict[str, Any]] = {}
    for item in files:
        module = str(item.get("module") or ".")
        stat = module_stats.setdefault(module, {"module": module, "files": 0, "functions": 0, "inbound": 0, "outbound": 0})
        stat["files"] += 1
        stat["functions"] += int(item.get("functionCount") or 0)
        stat["inbound"] += int(item.get("inboundInternalEdges") or 0)
        stat["outbound"] += int(item.get("outboundInternalEdges") or 0)

    entrypoints = [
        record
        for record in functions
        if len(record.callers) == 0 and len(record.callees) >= 2
    ]
    entrypoints.sort(key=lambda item: (-len(item.callees), item.file, item.line))

    isolated_count = sum(1 for record in functions if record.degree == 0)
    recommendations: List[str] = []
    if ambiguous_counter:
        recommendations.append("Resolve high-frequency ambiguous names with import/scope-aware parsing before treating every edge as factual.")
    if isolated_count:
        recommendations.append("Use isolated functions as a dead-code-or-entrypoint review queue; confirm with tests/routes before deletion.")
    if len(edges) > max(1, len(functions) * 3):
        recommendations.append("Default the UI to module lenses or selected-neighborhood views; full graph density is high.")
    if scan_meta.get("skippedLarge"):
        recommendations.append("Large files were skipped; raise maxFileBytes or add a parser-side chunking strategy for full coverage.")

    return {
        "purpose": "AI-friendly repo relation packet for orientation, refactor planning, test impact analysis, and hotspot review.",
        "claimCalibration": {
            "fact": "Nodes are detected functions/methods and edges are internal call-name matches from the scanned source snapshot.",
            "inference": "High-degree nodes and dense modules are likely coupling or orchestration hotspots.",
            "assumption": "Regex-derived non-Python edges are approximate until replaced with Tree-sitter or language-server data.",
            "unknown": "Runtime-only dynamic calls, dependency injection, reflection, and generated code may be missing.",
        },
        "topHotspots": [
            {
                "id": record.id,
                "name": record.name,
                "file": record.file,
                "line": record.line,
                "degree": record.degree,
                "callers": len(record.callers),
                "callees": len(record.callees),
            }
            for record in hotspots
        ],
        "entrypointCandidates": [
            {
                "id": record.id,
                "name": record.name,
                "file": record.file,
                "line": record.line,
                "callees": len(record.callees),
            }
            for record in entrypoints[:12]
        ],
        "denseModules": sorted(module_stats.values(), key=lambda item: (-int(item["functions"]), item["module"]))[:12],
        "ambiguousCallNames": [
            {"name": name, "count": count}
            for name, count in ambiguous_counter.most_common(20)
        ],
        "commonExternalCalls": [
            {"name": name, "count": count}
            for name, count in external_counter.most_common(20)
        ],
        "reviewQueues": {
            "isolatedFunctionCount": isolated_count,
            "highDegreeThreshold": 10,
            "ambiguousCallNameCount": len(ambiguous_counter),
        },
        "recommendedNextQueries": [
            "Show selected hotspot callers and callees before editing it.",
            "Filter to a module before judging coupling.",
            "Compare hotspots against tests to find unprotected behavior.",
            "Treat ambiguous-name edges as investigate, not proof.",
        ],
        "recommendations": recommendations,
    }


def cap_graph(functions: List[FunctionRecord], edges: List[Dict[str, Any]], max_nodes: int) -> tuple[List[FunctionRecord], List[Dict[str, Any]], bool]:
    if len(functions) <= max_nodes:
        return functions, edges, False
    selected = sorted(functions, key=lambda item: (-item.degree, -len(item.callers), item.file, item.line))[:max_nodes]
    selected_ids = {record.id for record in selected}
    selected_edges = [
        edge for edge in edges
        if str(edge.get("sourceId") or "") in selected_ids and str(edge.get("targetId") or "") in selected_ids
    ]
    return selected, selected_edges, True


def build_repo_graph(
    root: Path | str,
    *,
    repo_root: Path | str | None = None,
    max_nodes: int = 1600,
    max_files: int = 5000,
    max_file_bytes: int = 900_000,
    include_ambiguous: bool = False,
) -> Dict[str, Any]:
    resolved_root = Path(root).resolve()
    resolved_repo_root = Path(repo_root).resolve() if repo_root is not None else resolved_root
    max_nodes = max(50, min(5000, int(max_nodes or 1600)))
    max_files = max(50, min(20000, int(max_files or 5000)))
    max_file_bytes = max(64_000, min(10_000_000, int(max_file_bytes or 900_000)))
    files, scan_meta = source_files(
        resolved_root,
        max_file_bytes=max_file_bytes,
        max_files=max_files,
        relative_root=resolved_repo_root,
        ignore_root=resolved_repo_root,
    )

    functions: List[FunctionRecord] = []
    parse_errors: List[Dict[str, str]] = []
    for file in files:
        try:
            functions.extend(parse_file(file))
        except Exception as exc:  # noqa: BLE001
            parse_errors.append({"file": file.path, "message": str(exc)})
    functions = dedupe_functions(functions)
    edges = build_edges(functions, include_ambiguous=include_ambiguous, ambiguous_target_limit=4)
    files_out = file_summary(files, functions)
    ai_readout = build_ai_readout(functions, edges, files_out, scan_meta)
    capped_functions, capped_edges, truncated = cap_graph(functions, edges, max_nodes)

    nodes_out = [
        {
            "id": record.id,
            "name": record.name,
            "file": record.file,
            "line": record.line,
            "lang": record.lang,
            "type": record.type,
            "signature": record.signature,
            "module": module_key(record.file),
            "degree": record.degree,
            "callerCount": len(record.callers),
            "calleeCount": len(record.callees),
            "callers": sorted(record.callers),
            "callees": sorted(record.callees),
            "externalCalls": [
                {"name": name, "count": count}
                for name, count in record.external_calls.most_common(20)
            ],
            "ambiguousCalls": [
                {"name": name, "count": count}
                for name, count in record.ambiguous_calls.most_common(20)
            ],
        }
        for record in capped_functions
    ]

    return {
        "schemaVersion": "repo-function-graph/v1",
        "generatedAt": utc_now(),
        "root": str(resolved_root),
        "repoRoot": str(resolved_repo_root),
        "truncated": truncated,
        "stats": {
            "filesScanned": len(files),
            "functionsFound": len(functions),
            "nodesReturned": len(nodes_out),
            "internalEdges": len(edges),
            "edgesReturned": len(capped_edges),
            "parseErrorCount": len(parse_errors),
            **scan_meta,
        },
        "scanPolicy": {
            "maxNodes": max_nodes,
            "maxFiles": max_files,
            "maxFileBytes": max_file_bytes,
            "includeAmbiguousEdges": bool(include_ambiguous),
            "supportedExtensions": EXTENSIONS,
            "skippedPathParts": sorted(SKIP_PATH_PARTS),
        },
        "files": files_out,
        "nodes": nodes_out,
        "edges": capped_edges,
        "parseErrors": parse_errors[:100],
        "aiReadout": ai_readout,
    }
