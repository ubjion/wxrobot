"""本地持久化和运行日志使用的隐私保护工具。"""

from __future__ import annotations

import hashlib
import re


_SECRET_PATTERNS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]+", re.IGNORECASE),
    re.compile(
        r"\b(?:api[_-]?key|password|passwd|token)\s*[:=]\s*[^\s,，;；]+",
        re.IGNORECASE,
    ),
)
_EMAIL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    r"(?![A-Za-z0-9.-])"
)
_ID_CARD_PATTERN = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
_PHONE_PATTERN = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_WECHAT_ID_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])wxid_[A-Za-z0-9]+(?![A-Za-z0-9_])"
    r"|(?<![A-Za-z0-9_-])[A-Za-z0-9_-]+@chatroom(?![A-Za-z0-9_-])"
)


def redact_sensitive_text(text: str) -> str:
    """替换常见敏感值，同时保留对话意图。"""
    cleaned = text
    for pattern in _SECRET_PATTERNS:
        cleaned = pattern.sub("[SECRET]", cleaned)
    cleaned = _EMAIL_PATTERN.sub("[EMAIL]", cleaned)
    cleaned = _ID_CARD_PATTERN.sub("[ID_CARD]", cleaned)
    cleaned = _PHONE_PATTERN.sub("[PHONE]", cleaned)
    return _WECHAT_ID_PATTERN.sub("[USER]", cleaned)


def anonymous_id(value: str) -> str:
    """生成适合日志关联且不暴露原始标识的稳定指纹。"""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"session-{digest}"
