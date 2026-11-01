"""Shared message normalisation for training and inference.

The public phishing-email corpus used by ``ml/train_email_models.py`` is stored
already lower-cased and punctuation-tokenised, for example::

    "http : / / example . com"

Runtime text from ThreatLens is ordinary prose and may contain HTML. If the
training corpus and the live input were processed differently the classifier
would see a different token distribution. This module is therefore the single
normaliser used by both paths, and it is embedded in every saved text pipeline
as :class:`MessageNormalizer`.

The transform is intentionally conservative and idempotent:

1. decode HTML entities and drop markup/script/style content;
2. normalise Unicode (NFKC) and lower-case;
3. surround punctuation with spaces (the corpus convention);
4. collapse whitespace and remove control characters.

It does not stem, remove stop-words, rewrite URLs or translate text.
"""

from __future__ import annotations

import html
import re
import unicodedata
from html.parser import HTMLParser

from sklearn.base import BaseEstimator, TransformerMixin

_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")
_PUNCT_RE = re.compile(r"([^\w\s])")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SPACE_RE = re.compile(r"\s+")
_SKIP_TAGS = {"script", "style", "template", "noscript", "head"}


class _VisibleText(HTMLParser):
    """Collect visible text and skip invisible elements."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._hidden = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001 - HTMLParser API
        if tag in _SKIP_TAGS:
            self._hidden += 1
        else:
            self._parts.append(" ")

    def handle_startendtag(self, tag: str, attrs) -> None:  # noqa: ANN001
        self._parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._hidden:
            self._hidden -= 1
        else:
            self._parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._hidden:
            self._parts.append(data)

    def text(self) -> str:
        return " ".join(self._parts)


def strip_html(text: str) -> str:
    """Remove HTML markup without executing or rendering anything.

    Plain text that merely contains ``<`` or ``&`` is left alone unless it
    actually looks like a tag, so normal prose is not mangled.
    """
    if not text:
        return ""
    if _TAG_RE.search(text):
        parser = _VisibleText()
        try:
            parser.feed(text)
            parser.close()
            text = parser.text()
        except Exception:  # noqa: BLE001 - malformed markup falls back to a regex
            text = _TAG_RE.sub(" ", text)
    return html.unescape(text)


def normalize_message_text(text: str, max_chars: int | None = None) -> str:
    """Return corpus-compatible text for TF-IDF models.

    ``max_chars`` is applied after cleaning so that very large messages cannot
    dominate training time. The same bound must be used at inference.
    """
    if not text:
        return ""
    value = strip_html(str(text))
    value = unicodedata.normalize("NFKC", value)
    value = value.lower()
    value = _CONTROL_RE.sub(" ", value)
    value = _PUNCT_RE.sub(r" \1 ", value)
    value = _SPACE_RE.sub(" ", value).strip()
    if max_chars is not None and len(value) > max_chars:
        value = value[:max_chars].rsplit(" ", 1)[0].strip()
    return value


class MessageNormalizer(BaseEstimator, TransformerMixin):
    """Scikit-learn transformer that applies :func:`normalize_message_text`.

    It is a no-op during ``fit`` and never learns from the data, so it is safe
    to use inside a persisted pipeline for both training and inference.
    """

    def __init__(self, max_chars: int | None = None) -> None:
        self.max_chars = max_chars

    def fit(self, X, y=None):  # noqa: ANN001, N803 - sklearn API
        return self

    def transform(self, X):  # noqa: ANN001, N803 - sklearn API
        return [normalize_message_text(item, self.max_chars) for item in X]
