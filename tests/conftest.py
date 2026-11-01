from __future__ import annotations

from pathlib import Path

import pikepdf
import pytest

XMP_SAMPLE = b"""<?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
<rdf:Description rdf:about=""
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:xmp="http://ns.adobe.com/xap/1.0/"
    xmlns:xmpMM="http://ns.adobe.com/xap/1.0/mm/"
    xmlns:stEvt="http://ns.adobe.com/xap/1.0/sType/ResourceEvent#"
    xmlns:pdf="http://ns.adobe.com/pdf/1.3/"
    xmlns:foo="http://example.com/foo/">
<dc:title><rdf:Alt><rdf:li xml:lang="x-default">Report</rdf:li></rdf:Alt></dc:title>
<dc:creator><rdf:Seq><rdf:li>akiyama</rdf:li></rdf:Seq></dc:creator>
<dc:description><rdf:Alt><rdf:li xml:lang="x-default">Quarterly</rdf:li></rdf:Alt></dc:description>
<dc:subject><rdf:Bag><rdf:li>a</rdf:li><rdf:li>b</rdf:li></rdf:Bag></dc:subject>
<pdf:Keywords>a, b</pdf:Keywords>
<xmp:CreatorTool>Microsoft Word</xmp:CreatorTool>
<pdf:Producer>Word</pdf:Producer>
<xmp:CreateDate>2026-10-30T14:02:11+09:00</xmp:CreateDate>
<xmp:ModifyDate>2026-10-30T14:02:11+09:00</xmp:ModifyDate>
<xmpMM:DocumentID>uuid:1234</xmpMM:DocumentID>
<xmpMM:History><rdf:Seq><rdf:li rdf:parseType="Resource">
  <stEvt:action>saved</stEvt:action><stEvt:when>2026-10-30T14:02:11+09:00</stEvt:when>
</rdf:li></rdf:Seq></xmpMM:History>
<foo:Custom>bar</foo:Custom>
</rdf:Description>
<rdf:Description rdf:about="" xmlns:xmp="http://ns.adobe.com/xap/1.0/"
    xmp:MetadataDate="2026-10-30T14:02:11+09:00"/>
</rdf:RDF></x:xmpmeta><?xpacket end="w"?>"""


def make_pdf(path: Path, *, info: bool = True, xmp: bool = True, incremental: bool = False) -> Path:
    pdf = pikepdf.new()
    pdf.add_blank_page()
    if info:
        pdf.docinfo["/Title"] = "Report"
        pdf.docinfo["/Author"] = "akiyama"
        pdf.docinfo["/Subject"] = "Quarterly"
        pdf.docinfo["/Keywords"] = "a, b"
        pdf.docinfo["/Creator"] = "Microsoft Word"
        pdf.docinfo["/Producer"] = "Word"
        pdf.docinfo["/CreationDate"] = "D:20261030140211+09'00'"
        pdf.docinfo["/ModDate"] = "D:20261030140211+09'00'"
        pdf.docinfo["/Company"] = "ACME"
    if xmp:
        pdf.Root.Metadata = pdf.make_stream(
            XMP_SAMPLE, Type=pikepdf.Name.Metadata, Subtype=pikepdf.Name.XML
        )
    pdf.save(path)
    if incremental:
        _append_incremental_update(path)
    return path


def _append_incremental_update(path: Path) -> None:
    """Append a hand-written incremental update that replaces /Info.

    The original Info dictionary stays in the file body, as it would after
    a real "save" in Acrobat.
    """
    import re

    data = path.read_bytes()
    with pikepdf.open(path) as p:
        size = int(p.trailer["/Size"])
        root_ref = p.trailer["/Root"]
        root = f"{root_ref.objgen[0]} {root_ref.objgen[1]} R"
    prev = int(re.findall(rb"startxref\s+(\d+)", data)[-1])
    new_num = size
    if not data.endswith(b"\n"):
        data += b"\n"
    obj_offset = len(data)
    update = f"{new_num} 0 obj\n<< /Title (Report v2) /Producer (Acrobat) >>\nendobj\n".encode()
    xref_offset = obj_offset + len(update)
    update += (
        f"xref\n{new_num} 1\n{obj_offset:010d} 00000 n \ntrailer\n"
        f"<< /Size {new_num + 1} /Root {root} /Info {new_num} 0 R /Prev {prev} >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode()
    path.write_bytes(data + update)


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    return make_pdf(tmp_path / "sample.pdf")


@pytest.fixture
def plain_pdf(tmp_path: Path) -> Path:
    return make_pdf(tmp_path / "plain.pdf", info=False, xmp=False)


@pytest.fixture
def encrypted_pdf(tmp_path: Path) -> Path:
    src = make_pdf(tmp_path / "src.pdf")
    out = tmp_path / "enc.pdf"
    with pikepdf.open(src) as pdf:
        pdf.save(out, encryption=pikepdf.Encryption(owner="owner", user="user", R=6))
    return out
