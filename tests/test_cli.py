from __future__ import annotations

import json
from pathlib import Path

from clear_pdf_properties.cli import EXIT_INPUT, EXIT_OK, EXIT_REMAINING, main
from clear_pdf_properties.core import PdfDocument

from .conftest import make_pdf


def test_show_text(sample_pdf: Path, capsys):
    assert main(["show", str(sample_pdf)]) == EXIT_OK
    out = capsys.readouterr().out
    assert "Title          Report" in out
    assert "2026-10-30 14:02:11 +09:00" in out
    assert "xmpMM:History" in out


def test_show_json(sample_pdf: Path, capsys):
    assert main(["show", "--json", str(sample_pdf)]) == EXIT_OK
    data = json.loads(capsys.readouterr().out)
    assert data[0]["info"]["Author"] == "akiyama"
    assert data[0]["xmp"]["dc:creator"] == "akiyama"


def test_show_missing_file(tmp_path: Path, capsys):
    assert main(["show", str(tmp_path / "nope.pdf")]) == EXIT_INPUT


def test_clear_default_output(sample_pdf: Path, capsys):
    assert main(["clear", str(sample_pdf)]) == EXIT_OK
    dest = sample_pdf.with_name("sample_cleaned.pdf")
    assert dest.exists()
    assert PdfDocument.verify_cleared(dest) == {}
    with PdfDocument(sample_pdf) as doc:  # original untouched
        assert doc.info["Title"] == "Report"


def test_clear_in_place_multi(tmp_path: Path):
    a = make_pdf(tmp_path / "a.pdf")
    b = make_pdf(tmp_path / "b.pdf")
    assert main(["clear", "--in-place", str(a), str(b)]) == EXIT_OK
    assert PdfDocument.verify_cleared(a) == {}
    assert PdfDocument.verify_cleared(b) == {}


def test_clear_output_with_multiple_files_rejected(tmp_path: Path):
    a = make_pdf(tmp_path / "a.pdf")
    b = make_pdf(tmp_path / "b.pdf")
    assert main(["clear", "-o", str(tmp_path / "x.pdf"), str(a), str(b)]) == EXIT_INPUT


def test_clear_keep(sample_pdf: Path, tmp_path: Path):
    out = tmp_path / "k.pdf"
    rc = main(["clear", "-o", str(out), "--keep", "CreationDate,xmpMM:DocumentID", str(sample_pdf)])
    assert rc == EXIT_OK
    with PdfDocument(out) as doc:
        assert list(doc.info.keys()) == ["CreationDate"]
        assert [p.key for p in doc.xmp] == ["xmpMM:DocumentID"]


def test_clear_info_only(sample_pdf: Path, tmp_path: Path):
    out = tmp_path / "i.pdf"
    assert main(["clear", "--info-only", "-o", str(out), str(sample_pdf)]) == EXIT_OK
    with PdfDocument(out) as doc:
        assert doc.info == {}
        assert {p.key for p in doc.xmp} >= {"dc:title", "dc:creator"}


def test_clear_xmp_only(sample_pdf: Path, tmp_path: Path):
    out = tmp_path / "x.pdf"
    assert main(["clear", "--xmp-only", "-o", str(out), str(sample_pdf)]) == EXIT_OK
    with PdfDocument(out) as doc:
        assert doc.info["Title"] == "Report"
        assert doc.xmp == []


def test_clear_dry_run(sample_pdf: Path, capsys):
    assert main(["clear", "--dry-run", str(sample_pdf)]) == EXIT_OK
    assert not sample_pdf.with_name("sample_cleaned.pdf").exists()
    assert "dry run" in capsys.readouterr().out


def test_clear_encrypted(encrypted_pdf: Path, tmp_path: Path):
    out = tmp_path / "e.pdf"
    assert main(["clear", "-p", "owner", "-o", str(out), str(encrypted_pdf)]) == EXIT_OK
    assert PdfDocument.verify_cleared(out, "owner") == {}


def test_set_info_and_xmp(sample_pdf: Path, tmp_path: Path):
    out = tmp_path / "s.pdf"
    rc = main(
        [
            "set",
            "-o",
            str(out),
            str(sample_pdf),
            "Title=Hello",
            "Author=",
            "CreationDate=2020-01-02 03:04:05 +00:00",
            "xmp:CreatorTool=Tool",
            "xmp:ModifyDate=2021-01-01 00:00:00 +09:00",
        ]
    )
    assert rc == EXIT_OK
    with PdfDocument(out) as doc:
        assert doc.info["Title"] == "Hello"
        assert "Author" not in doc.info
        assert doc.info["CreationDate"] == "D:20200102030405+00'00'"
        x = {p.key: p.value for p in doc.xmp}
        assert x["dc:title"] == "Hello"
        assert "dc:creator" not in x
        assert x["xmp:CreateDate"] == "2020-01-02T03:04:05+00:00"
        assert x["xmp:CreatorTool"] == "Tool"
        assert x["xmp:ModifyDate"] == "2021-01-01T00:00:00+09:00"


def test_set_no_sync(sample_pdf: Path, tmp_path: Path):
    out = tmp_path / "s.pdf"
    assert main(["set", "--no-sync", "-o", str(out), str(sample_pdf), "Title=Hello"]) == EXIT_OK
    with PdfDocument(out) as doc:
        assert doc.info["Title"] == "Hello"
        assert {p.key: p.value for p in doc.xmp}["dc:title"] == "Report"


def test_set_bad_date(sample_pdf: Path):
    assert main(["set", str(sample_pdf), "CreationDate=yesterday"]) == EXIT_INPUT


def test_set_bad_assignment(sample_pdf: Path):
    assert main(["set", str(sample_pdf), "Title"]) == EXIT_INPUT


def test_exit_remaining_constant():
    assert EXIT_REMAINING == 2
