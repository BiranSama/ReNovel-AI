import os
import uuid
from pathlib import Path
from typing import Optional
import base64
import hashlib

from src.utils.logger import Log


class SecurityError(Exception):
    pass


def validate_uuid(value: str, field_name: str = "ID") -> str:
    try:
        uuid.UUID(value)
        return value
    except ValueError:
        raise SecurityError(f"Invalid {field_name} format: must be a valid UUID")


def safe_project_path(project_id: str, suffix: str) -> Path:
    validate_uuid(project_id, "project_id")
    
    base = Path("data/projects").resolve()
    target = (base / f"{project_id}{suffix}").resolve()
    
    if not str(target).startswith(str(base)):
        raise SecurityError(f"Path traversal detected in project path")
    
    return target


def safe_data_path(project_id: str, subdir: str, filename: str) -> Path:
    validate_uuid(project_id, "project_id")
    
    safe_filename = Path(filename).name
    
    base = Path(f"data/{subdir}").resolve()
    target = (base / project_id / safe_filename).resolve()
    
    if not str(target).startswith(str(base)):
        raise SecurityError(f"Path traversal detected in data path")
    
    return target


def sanitize_filename(filename: str) -> str:
    dangerous_chars = ['/', '\\', '..', '\x00']
    result = filename
    for char in dangerous_chars:
        result = result.replace(char, '_')
    
    max_length = 255
    if len(result) > max_length:
        name, ext = os.path.splitext(result)
        result = name[:max_length - len(ext)] + ext
    
    return result


def mask_api_key(api_key: str, visible_chars: int = 4) -> str:
    if not api_key:
        return ""
    if len(api_key) <= visible_chars * 2:
        return "*" * len(api_key)
    return f"{api_key[:visible_chars]}...{api_key[-visible_chars:]}"


def obfuscate_key(key: str) -> str:
    if not key:
        return ""
    return base64.b64encode(key.encode()).decode()


def deobfuscate_key(obfuscated: str) -> str:
    if not obfuscated:
        return ""
    try:
        return base64.b64decode(obfuscated.encode()).decode()
    except Exception:
        return ""


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def validate_input_length(value: str, max_length: int, field_name: str = "input") -> str:
    if len(value) > max_length:
        raise SecurityError(f"{field_name} exceeds maximum length of {max_length}")
    return value


def sanitize_html_input(value: str) -> str:
    dangerous_patterns = ['<script', 'javascript:', 'onerror=', 'onload=']
    result = value.lower()
    for pattern in dangerous_patterns:
        if pattern in result:
            raise SecurityError(f"Potentially dangerous input detected")
    return value
