"""Core PDF property operations (GUI/CLI independent)."""

from . import dates
from .document import (
    DocumentError,
    DocumentStatus,
    NotEditable,
    PasswordRequired,
    PdfDocument,
    inspect_file,
)
from .info import DATE_KEYS, STANDARD_KEYS
from .xmp import INFO_TO_XMP, XMP_DATE_KEYS, XmpProperty

__all__ = [
    "dates",
    "DocumentError",
    "DocumentStatus",
    "NotEditable",
    "PasswordRequired",
    "PdfDocument",
    "inspect_file",
    "DATE_KEYS",
    "STANDARD_KEYS",
    "INFO_TO_XMP",
    "XMP_DATE_KEYS",
    "XmpProperty",
]
