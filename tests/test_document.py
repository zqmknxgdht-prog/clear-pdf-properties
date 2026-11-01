from __future__ import annotations

from pathlib import Path

import pikepdf
import pytest

from clear_pdf_properties.core import (
    NotEditable,
    PasswordRequired,
    PdfDocument,
    inspect_file,
)

from .conftest import make_pdf


def xmp_dict(doc: PdfDocument) -> dict[str, str]:
    return {p.key: p.value for p in doc.xmp}


# ---- reading ----------------------------------------------------------------


def test_read_info_order_and_custom(sample_pdf: Path):
    with PdfDocument(sample_pdf) as doc:
        keys = list(doc.info.keys())
    assert keys[:8] == [
        "Title",
        "Author",
        "Subject",
        "Keywords",
        "Creator",
        "Producer",
        "CreationDate",
        "ModDate",
    ]
    assert keys[8] == "Company"


def test_read_xmp_structures(sample_pdf: Path):
    with PdfDocument(sample_pdf) as doc:
        x = xmp_dict(doc)
        props = {p.key: p for p in doc.xmp}
    assert x["dc:title"] == "Report"
    assert x["dc:creator"] == "akiyama"
    assert x["dc:subject"] == "a; b"
    assert x["xmpMM:History"] == "{stEvt:action=saved, stEvt:when=2026-10-30T14:02:11+09:00}"
    assert x["foo:Custom"] == "bar"
    assert x["xmp:MetadataDate"] == "2026-10-30T14:02:11+09:00"  # attribute form
    assert props["dc:title"].simple is True
    assert props["xmpMM:History"].simple is False


def test_status_flags(sample_pdf: Path, plain_pdf: Path, tmp_path: Path):
    st = inspect_file(sample_pdf)
    assert st.encrypted is False and st.editable is True
    assert st.incremental_updates is False
    assert st.has_xmp is True
    assert inspect_file(plain_pdf).has_xmp is False
    inc = make_pdf(tmp_path / "inc.pdf", incremental=True)
    st2 = inspect_file(inc)
    assert st2.incremental_updates is True
    assert st2.info["Title"] == "Report v2"


# ---- Info editing -----------------------------------------------------------


def test_delete_info_with_sync(sample_pdf: Path, tmp_path: Path):
    out = tmp_path / "out.pdf"
    with PdfDocument(sample_pdf) as doc:
        doc.delete_info("Author")
        doc.save(out)
    with PdfDocument(out) as doc:
        assert "Author" not in doc.info
        assert "dc:creator" not in xmp_dict(doc)
        assert "dc:title" in xmp_dict(doc)


def test_delete_info_without_sync(sample_pdf: Path, tmp_path: Path):
    out = tmp_path / "out.pdf"
    with PdfDocument(sample_pdf) as doc:
        doc.delete_info("Author", sync=False)
        doc.save(out)
    with PdfDocument(out) as doc:
        assert "Author" not in doc.info
        assert xmp_dict(doc)["dc:creator"] == "akiyama"


def test_set_info_with_sync_and_dates(sample_pdf: Path, tmp_path: Path):
    out = tmp_path / "out.pdf"
    with PdfDocument(sample_pdf) as doc:
        doc.set_info("Title", "New Title")
        doc.set_info("CreationDate", "D:20200101000000+00'00'")
        doc.save(out)
    with PdfDocument(out) as doc:
        assert doc.info["Title"] == "New Title"
        assert doc.info["CreationDate"] == "D:20200101000000+00'00'"
        x = xmp_dict(doc)
        assert x["dc:title"] == "New Title"
        assert x["xmp:CreateDate"] == "2020-01-01T00:00:00+00:00"


def test_set_info_empty_deletes(sample_pdf: Path, tmp_path: Path):
    out = tmp_path / "out.pdf"
    with PdfDocument(sample_pdf) as doc:
        doc.set_info("Producer", "")
        doc.save(out)
    with PdfDocument(out) as doc:
        assert "Producer" not in doc.info
        assert "pdf:Producer" not in xmp_dict(doc)
        raw = out.read_bytes()
    assert b"/Producer" not in raw


def test_clear_info_sync_keeps_unmirrored_xmp(sample_pdf: Path, tmp_path: Path):
    out = tmp_path / "out.pdf"
    with PdfDocument(sample_pdf) as doc:
        doc.clear_info()
        doc.save(out)
    with PdfDocument(out) as doc:
        assert doc.info == {}
        x = xmp_dict(doc)
        for gone in ("dc:title", "dc:creator", "pdf:Producer", "xmp:CreateDate", "xmp:ModifyDate"):
            assert gone not in x
        assert x["xmpMM:DocumentID"] == "uuid:1234"
        assert "xmpMM:History" in x
    with pikepdf.open(out) as p:
        assert "/Info" not in p.trailer


# ---- XMP editing ------------------------------------------------------------


def test_delete_xmp_single(sample_pdf: Path, tmp_path: Path):
    out = tmp_path / "out.pdf"
    with PdfDocument(sample_pdf) as doc:
        doc.delete_xmp("xmpMM:History")
        doc.delete_xmp("{http://example.com/foo/}Custom")
        doc.save(out)
    with PdfDocument(out) as doc:
        x = xmp_dict(doc)
        assert "xmpMM:History" not in x
        assert "foo:Custom" not in x
        assert x["dc:title"] == "Report"
        assert doc.info["Title"] == "Report"  # XMP ops never touch Info


def test_set_xmp(sample_pdf: Path, tmp_path: Path):
    out = tmp_path / "out.pdf"
    with PdfDocument(sample_pdf) as doc:
        doc.set_xmp("xmp:CreatorTool", "Nothing")
        doc.set_xmp("dc:creator", "someone")
        doc.save(out)
    with PdfDocument(out) as doc:
        x = xmp_dict(doc)
        assert x["xmp:CreatorTool"] == "Nothing"
        assert x["dc:creator"] == "someone"


def test_clear_xmp_removes_stream(sample_pdf: Path, tmp_path: Path):
    out = tmp_path / "out.pdf"
    with PdfDocument(sample_pdf) as doc:
        doc.clear_xmp()
        doc.save(out)
    with pikepdf.open(out) as p:
        assert "/Metadata" not in p.Root
    with PdfDocument(out) as doc:
        assert doc.xmp == []
        assert doc.info["Title"] == "Report"


# ---- full clear + verification ---------------------------------------------


def test_clear_all_leaves_nothing(sample_pdf: Path, tmp_path: Path):
    out = tmp_path / "out.pdf"
    with PdfDocument(sample_pdf) as doc:
        doc.clear_all()
        doc.save(out)
    assert PdfDocument.verify_cleared(out) == {}
    raw = out.read_bytes()
    for needle in (b"akiyama", b"Microsoft Word", b"uuid:1234", b"ACME"):
        assert needle not in raw


def test_full_rewrite_drops_incremental_history(tmp_path: Path):
    src = make_pdf(tmp_path / "inc.pdf", incremental=True)
    assert b"Report v2" in src.read_bytes() and b"(Report)" in src.read_bytes()
    out = tmp_path / "out.pdf"
    with PdfDocument(src) as doc:
        doc.clear_all()
        doc.save(out)
    raw = out.read_bytes()
    assert raw.count(b"startxref") == 1
    assert b"Report" not in raw
    assert inspect_file(out).incremental_updates is False


def test_save_in_place(sample_pdf: Path):
    with PdfDocument(sample_pdf) as doc:
        doc.delete_info("Title")
        doc.save()
    with PdfDocument(sample_pdf) as doc:
        assert "Title" not in doc.info


def test_save_does_not_add_producer(plain_pdf: Path, tmp_path: Path):
    out = tmp_path / "out.pdf"
    with PdfDocument(plain_pdf) as doc:
        doc.set_info("Title", "x")
        doc.save(out)
    with PdfDocument(out) as doc:
        assert "Producer" not in doc.info
        assert "pdf:Producer" not in xmp_dict(doc)


# ---- encryption -------------------------------------------------------------


def test_encrypted_requires_password(encrypted_pdf: Path):
    with pytest.raises(PasswordRequired):
        PdfDocument(encrypted_pdf)
    with pytest.raises(PasswordRequired):
        PdfDocument(encrypted_pdf, password="wrong")


def test_encrypted_owner_password_edits(encrypted_pdf: Path, tmp_path: Path):
    out = tmp_path / "out.pdf"
    with PdfDocument(encrypted_pdf, password="owner") as doc:
        assert doc.encrypted and doc.editable
        doc.clear_all()
        doc.save(out)
    # Encryption is preserved: same passwords still apply.
    with pytest.raises(PasswordRequired):
        PdfDocument(out)
    assert PdfDocument.verify_cleared(out, password="user") == {}
    with PdfDocument(out, password="owner") as doc:
        assert doc.encrypted


def test_encrypted_user_password_not_editable(encrypted_pdf: Path):
    with PdfDocument(encrypted_pdf, password="user") as doc:
        assert doc.encrypted
        assert doc.info["Title"] == "Report"
        if not doc.editable:
            with pytest.raises(NotEditable):
                doc.delete_info("Title")
