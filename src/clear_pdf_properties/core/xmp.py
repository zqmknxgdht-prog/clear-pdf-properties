"""Read / set / delete XMP metadata (catalog ``/Metadata`` stream).

Reading is done with our own XML parser so that structured properties
(``xmpMM:History`` etc.) are shown faithfully; pikepdf's reader flattens
them lossily. Writing and deleting go through pikepdf.
"""

from __future__ import annotations

import re
import warnings
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import pikepdf

__all__ = [
    "XmpProperty",
    "KNOWN_NAMESPACES",
    "INFO_TO_XMP",
    "XMP_DATE_KEYS",
    "has_xmp",
    "read_xmp",
    "set_xmp",
    "delete_xmp",
    "clear_xmp",
    "resolve_key",
]

RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
XML_NS = "http://www.w3.org/XML/1998/namespace"

# prefix -> namespace URI
KNOWN_NAMESPACES: dict[str, str] = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "xmp": "http://ns.adobe.com/xap/1.0/",
    "xmpMM": "http://ns.adobe.com/xap/1.0/mm/",
    "xmpRights": "http://ns.adobe.com/xap/1.0/rights/",
    "xmpTPg": "http://ns.adobe.com/xap/1.0/t/pg/",
    "xmpidq": "http://ns.adobe.com/xmp/Identifier/qual/1.0/",
    "pdf": "http://ns.adobe.com/pdf/1.3/",
    "pdfx": "http://ns.adobe.com/pdfx/1.3/",
    "pdfaid": "http://www.aiim.org/pdfa/ns/id/",
    "pdfuaid": "http://www.aiim.org/pdfua/ns/id/",
    "pdfaExtension": "http://www.aiim.org/pdfa/ns/extension/",
    "photoshop": "http://ns.adobe.com/photoshop/1.0/",
    "stEvt": "http://ns.adobe.com/xap/1.0/sType/ResourceEvent#",
    "stRef": "http://ns.adobe.com/xap/1.0/sType/ResourceRef#",
    "stDim": "http://ns.adobe.com/xap/1.0/sType/Dimensions#",
    "Iptc4xmpCore": "http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/",
    "illustrator": "http://ns.adobe.com/illustrator/1.0/",
    "prism": "http://prismstandard.org/namespaces/basic/2.0/",
}
_URI_TO_PREFIX: dict[str, str] = {v: k for k, v in KNOWN_NAMESPACES.items()}

# Info key -> XMP properties that mirror it (first is the primary one).
INFO_TO_XMP: dict[str, tuple[str, ...]] = {
    "Title": ("dc:title",),
    "Author": ("dc:creator",),
    "Subject": ("dc:description",),
    "Keywords": ("pdf:Keywords", "dc:subject"),
    "Creator": ("xmp:CreatorTool",),
    "Producer": ("pdf:Producer",),
    "CreationDate": ("xmp:CreateDate",),
    "ModDate": ("xmp:ModifyDate", "xmp:MetadataDate"),
}
XMP_DATE_KEYS: frozenset[str] = frozenset({"xmp:CreateDate", "xmp:ModifyDate", "xmp:MetadataDate"})

# XMP properties whose value is an ordered/unordered array of simple strings.
_ARRAY_KEYS: frozenset[str] = frozenset({"dc:creator", "dc:subject", "pdf:Keywords"})


@dataclass(frozen=True)
class XmpProperty:
    key: str  # "dc:title"
    clark: str  # "{http://purl.org/dc/elements/1.1/}title"
    value: str  # flattened display value
    simple: bool  # True if a plain text value (editable); False for arrays/structs


def _rdf(local: str) -> str:
    return f"{{{RDF_NS}}}{local}"


def has_xmp(pdf: pikepdf.Pdf) -> bool:
    return "/Metadata" in pdf.Root


def _prefix_map(raw: bytes) -> dict[str, str]:
    """Namespace URI -> prefix, from the document's own xmlns declarations."""
    found: dict[str, str] = {}
    for prefix, uri in re.findall(rb'xmlns:([A-Za-z0-9_.-]+)="([^"]*)"', raw):
        found.setdefault(uri.decode("utf-8", "replace"), prefix.decode("ascii", "replace"))
    merged = dict(_URI_TO_PREFIX)
    merged.update(found)
    return merged


def _split_clark(tag: str) -> tuple[str, str]:
    if tag.startswith("{"):
        uri, local = tag[1:].split("}", 1)
        return uri, local
    return "", tag


def _qualify(tag: str, uri_to_prefix: dict[str, str]) -> str:
    uri, local = _split_clark(tag)
    if not uri:
        return local
    prefix = uri_to_prefix.get(uri)
    return f"{prefix}:{local}" if prefix else tag


def _flatten(el: ET.Element, uri_to_prefix: dict[str, str]) -> tuple[str, bool]:
    """Return (display text, is_simple) for a property element."""
    children = list(el)
    # Array containers
    for kind in ("Alt", "Seq", "Bag"):
        arr = el.find(_rdf(kind))
        if arr is not None:
            items = [_flatten(li, uri_to_prefix)[0] for li in arr.findall(_rdf("li"))]
            if kind == "Alt":
                # Prefer x-default language entry.
                for li in arr.findall(_rdf("li")):
                    if li.get(f"{{{XML_NS}}}lang") == "x-default":
                        return _flatten(li, uri_to_prefix)[0], True
                return (items[0] if items else ""), True
            return "; ".join(items), False
    # Struct (parseType="Resource" or nested rdf:Description)
    if el.get(_rdf("parseType")) == "Resource" or el.find(_rdf("Description")) is not None:
        holder = el.find(_rdf("Description"))
        holder = holder if holder is not None else el
        parts = []
        for k, v in holder.attrib.items():
            if k.startswith(f"{{{RDF_NS}}}"):
                continue
            parts.append(f"{_qualify(k, uri_to_prefix)}={v}")
        for child in holder:
            name = _qualify(child.tag, uri_to_prefix)
            parts.append(f"{name}={_flatten(child, uri_to_prefix)[0]}")
        return "{" + ", ".join(parts) + "}", False
    if children:
        # Unknown nesting: join children.
        joined = "; ".join(
            f"{_qualify(c.tag, uri_to_prefix)}={_flatten(c, uri_to_prefix)[0]}" for c in children
        )
        return joined, False
    # Resource reference via attribute (e.g. <foo rdf:resource="..."/>)
    res = el.get(_rdf("resource"))
    if res is not None and not (el.text or "").strip():
        return res, True
    return (el.text or "").strip(), True


def read_xmp(pdf: pikepdf.Pdf) -> list[XmpProperty]:
    """Return all XMP properties in document order. Empty list if none or unparsable."""
    if not has_xmp(pdf):
        return []
    try:
        raw = pdf.Root.Metadata.read_bytes()
    except Exception:
        return []
    if not raw.strip():
        return []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        msg = "XMP ストリームを XML として解析できません"
        return [XmpProperty("(parse error)", "", msg, False)]
    uri_to_prefix = _prefix_map(raw)
    props: list[XmpProperty] = []
    seen: set[str] = set()
    # Only rdf:Description elements that are direct children of rdf:RDF hold
    # top-level properties; nested ones are struct holders.
    top_level = [
        desc for rdf_el in root.iter(_rdf("RDF")) for desc in rdf_el.findall(_rdf("Description"))
    ]
    for desc in top_level:
        for k, v in desc.attrib.items():
            if k.startswith(f"{{{RDF_NS}}}") or k.startswith(f"{{{XML_NS}}}"):
                continue
            key = _qualify(k, uri_to_prefix)
            if key not in seen:
                seen.add(key)
                props.append(XmpProperty(key, k, v, True))
        for child in desc:
            key = _qualify(child.tag, uri_to_prefix)
            value, simple = _flatten(child, uri_to_prefix)
            if key not in seen:
                seen.add(key)
                props.append(XmpProperty(key, child.tag, value, simple))
    return props


def resolve_key(key: str) -> str:
    """Turn ``prefix:local`` into Clark notation using KNOWN_NAMESPACES.

    Clark-form input is returned unchanged. Unknown prefixes raise KeyError.
    """
    if key.startswith("{"):
        return key
    if ":" not in key:
        raise KeyError(f"XMP キーは prefix:name 形式で指定してください: {key!r}")
    prefix, local = key.split(":", 1)
    uri = KNOWN_NAMESPACES.get(prefix)
    if uri is None:
        raise KeyError(f"未知の XMP 名前空間プレフィックスです: {prefix!r}")
    return f"{{{uri}}}{local}"


def _open(pdf: pikepdf.Pdf):
    return pdf.open_metadata(set_pikepdf_as_editor=False, update_docinfo=False)


def set_xmp(pdf: pikepdf.Pdf, key: str, value: str) -> None:
    """Set a simple XMP property. Empty value deletes it.

    ``key`` may be ``prefix:local`` (known prefixes) or Clark notation.
    """
    if value == "":
        delete_xmp(pdf, key)
        return
    clark = resolve_key(key)
    prefixed = _qualify(clark, _URI_TO_PREFIX)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with _open(pdf) as m:
            if prefixed in _ARRAY_KEYS:
                m[clark] = [value]
            else:
                m[clark] = value


def delete_xmp(pdf: pikepdf.Pdf, key: str) -> bool:
    """Delete one XMP property. Returns True if it existed."""
    if not has_xmp(pdf):
        return False
    clark = resolve_key(key)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with _open(pdf) as m:
            if clark not in m:
                return False
            del m[clark]
    return True


def clear_xmp(pdf: pikepdf.Pdf) -> bool:
    """Remove the whole /Metadata stream. Returns True if it existed."""
    if not has_xmp(pdf):
        return False
    del pdf.Root["/Metadata"]
    return True
