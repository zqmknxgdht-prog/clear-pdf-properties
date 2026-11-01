"""Document façade: open / inspect / edit / save a PDF's properties.

GUI and CLI use only this module (plus ``dates`` for user-format conversion);
they never import pikepdf directly.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pikepdf

from . import dates, info, xmp

__all__ = [
    "DocumentError",
    "PasswordRequired",
    "NotEditable",
    "DocumentStatus",
    "PdfDocument",
    "inspect_file",
]


class DocumentError(Exception):
    """Base class for errors raised by this module."""


class PasswordRequired(DocumentError):
    """The PDF is encrypted and the given password (if any) is wrong."""


class NotEditable(DocumentError):
    """Opened with a user password only; metadata cannot be modified."""


@dataclass
class DocumentStatus:
    path: Path
    encrypted: bool
    editable: bool
    incremental_updates: bool
    pdf_version: str
    pages: int
    info: dict[str, str] = field(default_factory=dict)
    xmp: list[xmp.XmpProperty] = field(default_factory=list)

    @property
    def has_xmp(self) -> bool:
        return bool(self.xmp)


def _count_startxref(path: Path) -> int:
    data = path.read_bytes()
    return data.count(b"startxref")


class PdfDocument:
    """A PDF opened for property editing. Changes stay in memory until ``save``."""

    def __init__(self, path: str | os.PathLike[str], password: str | None = None):
        self.path = Path(path)
        try:
            self._pdf = pikepdf.open(self.path, password=password or "")
        except pikepdf.PasswordError as e:
            raise PasswordRequired(str(e)) from e
        except FileNotFoundError as e:
            raise DocumentError(f"ファイルが見つかりません: {self.path}") from e
        except (pikepdf.PdfError, OSError) as e:
            raise DocumentError(f"PDF を開けません: {e}") from e
        self.encrypted = self._pdf.is_encrypted
        # With only a user password pikepdf opens read-only w.r.t. permissions,
        # but can still rewrite. We treat "owner password missing" as not editable
        # when the document disallows modification.
        self.editable = True
        if self.encrypted:
            perms = self._pdf.allow
            self.editable = bool(perms.modify_other or perms.modify_annotation or perms.modify_form)
            # If opened with the owner password, pikepdf reports all permissions.
            if self._pdf.owner_password_matched:
                self.editable = True
        self.incremental_updates = _count_startxref(self.path) > 1
        self.dirty = False

    # ---- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        self._pdf.close()

    def __enter__(self) -> PdfDocument:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- inspection ---------------------------------------------------------

    @property
    def info(self) -> dict[str, str]:
        return info.read_info(self._pdf)

    @property
    def xmp(self) -> list[xmp.XmpProperty]:
        return xmp.read_xmp(self._pdf)

    def status(self) -> DocumentStatus:
        return DocumentStatus(
            path=self.path,
            encrypted=self.encrypted,
            editable=self.editable,
            incremental_updates=self.incremental_updates,
            pdf_version=self._pdf.pdf_version,
            pages=len(self._pdf.pages),
            info=self.info,
            xmp=self.xmp,
        )

    # ---- editing: Info ------------------------------------------------------

    def _check_editable(self) -> None:
        if not self.editable:
            raise NotEditable("所有者パスワードなしでは編集できません")

    def set_info(self, key: str, value: str, *, sync: bool = True) -> None:
        """Set an Info entry (value in Info format: dates as ``D:...``).

        With ``sync`` the mirrored XMP keys are updated too (dates converted).
        Empty value deletes.
        """
        self._check_editable()
        info.set_info(self._pdf, key, value)
        if sync:
            for xkey in xmp.INFO_TO_XMP.get(key, ()):
                if value == "":
                    xmp.delete_xmp(self._pdf, xkey)
                elif key in info.DATE_KEYS:
                    try:
                        xmp.set_xmp(self._pdf, xkey, dates.info_to_xmp(value))
                    except dates.DateParseError:
                        xmp.set_xmp(self._pdf, xkey, value)
                else:
                    xmp.set_xmp(self._pdf, xkey, value)
        self.dirty = True

    def delete_info(self, key: str, *, sync: bool = True) -> None:
        self._check_editable()
        info.delete_info(self._pdf, key)
        if sync:
            for xkey in xmp.INFO_TO_XMP.get(key, ()):
                xmp.delete_xmp(self._pdf, xkey)
        self.dirty = True

    def clear_info(self, *, sync: bool = True) -> None:
        self._check_editable()
        keys = list(self.info.keys())
        info.clear_info(self._pdf)
        if sync:
            for key in keys:
                for xkey in xmp.INFO_TO_XMP.get(key, ()):
                    xmp.delete_xmp(self._pdf, xkey)
        self.dirty = True

    # ---- editing: XMP -------------------------------------------------------

    def set_xmp(self, key: str, value: str) -> None:
        self._check_editable()
        xmp.set_xmp(self._pdf, key, value)
        self.dirty = True

    def delete_xmp(self, key: str) -> None:
        self._check_editable()
        xmp.delete_xmp(self._pdf, key)
        self.dirty = True

    def clear_xmp(self) -> None:
        self._check_editable()
        xmp.clear_xmp(self._pdf)
        self.dirty = True

    def clear_all(self) -> None:
        self.clear_info(sync=False)
        self.clear_xmp()

    # ---- saving -------------------------------------------------------------

    def save(self, out_path: str | os.PathLike[str] | None = None) -> Path:
        """Write the document (always a full rewrite). Returns the written path.

        ``out_path=None`` overwrites the original file atomically.
        """
        self._check_editable()
        target = Path(out_path) if out_path is not None else self.path
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".cpp-", suffix=".pdf", dir=target.parent)
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            # encryption=True keeps the input's encryption (same passwords and
            # permissions); an unencrypted input stays unencrypted.
            self._pdf.save(tmp, deterministic_id=False, encryption=self.encrypted)
            os.replace(tmp, target)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        self.dirty = False
        return target

    # ---- verification -------------------------------------------------------

    @staticmethod
    def verify_cleared(path: str | os.PathLike[str], password: str | None = None) -> dict[str, str]:
        """Reopen ``path`` and return any remaining Info/XMP properties (empty = clean)."""
        with PdfDocument(path, password) as doc:
            remaining = {f"Info:{k}": v for k, v in doc.info.items()}
            for p in doc.xmp:
                remaining[f"XMP:{p.key}"] = p.value
            return remaining


def inspect_file(path: str | os.PathLike[str], password: str | None = None) -> DocumentStatus:
    with PdfDocument(path, password) as doc:
        return doc.status()
