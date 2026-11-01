"""Read / set / delete entries of the PDF Info dictionary (trailer ``/Info``)."""

from __future__ import annotations

import pikepdf

__all__ = [
    "STANDARD_KEYS",
    "DATE_KEYS",
    "read_info",
    "set_info",
    "delete_info",
    "clear_info",
]

STANDARD_KEYS: tuple[str, ...] = (
    "Title",
    "Author",
    "Subject",
    "Keywords",
    "Creator",
    "Producer",
    "CreationDate",
    "ModDate",
)
DATE_KEYS: frozenset[str] = frozenset({"CreationDate", "ModDate"})


def _name(key: str) -> str:
    return key if key.startswith("/") else "/" + key


def _to_text(value: pikepdf.Object) -> str:
    if isinstance(value, pikepdf.String):
        return str(value)
    if isinstance(value, pikepdf.Name):
        return str(value)
    try:
        return str(value)
    except Exception:  # pragma: no cover - defensive
        return repr(value)


def read_info(pdf: pikepdf.Pdf) -> dict[str, str]:
    """Return all Info entries as ``{key_without_slash: text}``.

    Standard keys come first in canonical order, followed by custom keys
    in document order.
    """
    info = pdf.trailer.get("/Info")
    if info is None or not isinstance(info, pikepdf.Dictionary):
        return {}
    raw = {str(k)[1:]: _to_text(v) for k, v in info.items()}
    ordered: dict[str, str] = {}
    for k in STANDARD_KEYS:
        if k in raw:
            ordered[k] = raw.pop(k)
    ordered.update(raw)
    return ordered


def set_info(pdf: pikepdf.Pdf, key: str, value: str) -> None:
    """Set an Info entry. Empty value deletes the key (never leaves an empty string)."""
    if value == "":
        delete_info(pdf, key)
        return
    if "/Info" not in pdf.trailer or not isinstance(pdf.trailer.Info, pikepdf.Dictionary):
        pdf.trailer.Info = pdf.make_indirect(pikepdf.Dictionary())
    pdf.trailer.Info[_name(key)] = pikepdf.String(value)


def delete_info(pdf: pikepdf.Pdf, key: str) -> bool:
    """Delete one Info entry. Returns True if it existed."""
    info = pdf.trailer.get("/Info")
    if info is None or not isinstance(info, pikepdf.Dictionary):
        return False
    name = _name(key)
    if name not in info:
        return False
    del info[name]
    if len(info.keys()) == 0:
        del pdf.trailer["/Info"]
    return True


def clear_info(pdf: pikepdf.Pdf) -> int:
    """Remove the whole Info dictionary. Returns the number of entries removed."""
    info = pdf.trailer.get("/Info")
    if info is None or not isinstance(info, pikepdf.Dictionary):
        return 0
    n = len(info.keys())
    del pdf.trailer["/Info"]
    return n
