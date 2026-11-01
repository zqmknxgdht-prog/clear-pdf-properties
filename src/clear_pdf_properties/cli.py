"""Command-line interface: show / clear / set.

Exit codes: 0 success, 1 input error, 2 verification found remaining properties.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .core import (
    DATE_KEYS,
    STANDARD_KEYS,
    XMP_DATE_KEYS,
    DocumentError,
    PdfDocument,
    dates,
    inspect_file,
)

EXIT_OK = 0
EXIT_INPUT = 1
EXIT_REMAINING = 2


def _err(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)


def _out_path(src: Path, out: str | None, in_place: bool, suffix: str, multi: bool) -> Path:
    if in_place:
        return src
    if out and not multi:
        return Path(out)
    return src.with_name(f"{src.stem}{suffix}{src.suffix}")


# ---- show -------------------------------------------------------------------


def cmd_show(args: argparse.Namespace) -> int:
    rc = EXIT_OK
    results = []
    for f in args.files:
        try:
            st = inspect_file(f, args.password)
        except DocumentError as e:
            _err(f"{f}: {e}")
            rc = EXIT_INPUT
            continue
        if args.json:
            results.append(
                {
                    "path": str(st.path),
                    "encrypted": st.encrypted,
                    "editable": st.editable,
                    "incremental_updates": st.incremental_updates,
                    "pdf_version": st.pdf_version,
                    "pages": st.pages,
                    "info": st.info,
                    "xmp": {p.key: p.value for p in st.xmp},
                }
            )
            continue
        print(f"== {st.path}")
        print(
            f"   PDF {st.pdf_version}, {st.pages} page(s), "
            f"encrypted={'yes' if st.encrypted else 'no'}, "
            f"incremental updates={'yes' if st.incremental_updates else 'no'}"
        )
        print("-- Info")
        if not st.info:
            print("   (none)")
        for k, v in st.info.items():
            shown = v
            if k in DATE_KEYS:
                try:
                    shown = f"{dates.info_to_user(v)}  ({v})"
                except dates.DateParseError:
                    pass
            print(f"   {k:<14} {shown}")
        print(f"-- XMP ({len(st.xmp)})")
        if not st.xmp:
            print("   (none)")
        for p in st.xmp:
            print(f"   {p.key:<22} {p.value}")
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    return rc


# ---- clear ------------------------------------------------------------------


def cmd_clear(args: argparse.Namespace) -> int:
    if args.output and len(args.files) > 1:
        _err(
            "-o/--output は単一ファイルのときのみ。"
            "複数ファイルには --in-place か --suffix を使ってください"
        )
        return EXIT_INPUT
    keep = {k.strip() for k in (args.keep or "").split(",") if k.strip()}
    rc = EXIT_OK
    for f in args.files:
        src = Path(f)
        try:
            with PdfDocument(src, args.password) as doc:
                if not args.xmp_only:
                    for key in list(doc.info.keys()):
                        if key in keep:
                            continue
                        doc.delete_info(key, sync=not args.no_sync and not args.info_only)
                if not args.info_only:
                    if keep:
                        for p in doc.xmp:
                            if p.key not in keep and p.clark:
                                doc.delete_xmp(p.clark)
                    else:
                        doc.clear_xmp()
                dest = _out_path(src, args.output, args.in_place, args.suffix, len(args.files) > 1)
                if args.dry_run:
                    print(f"{src} -> {dest} (dry run)")
                    print(f"   remaining Info: {list(doc.info.keys())}")
                    print(f"   remaining XMP:  {[p.key for p in doc.xmp]}")
                    continue
                doc.save(dest)
        except DocumentError as e:
            _err(f"{src}: {e}")
            rc = max(rc, EXIT_INPUT)
            continue
        remaining = PdfDocument.verify_cleared(dest, args.password)
        unexpected = {}
        for k, v in remaining.items():
            layer, key = k.split(":", 1)
            if key in keep:
                continue
            if layer == "Info" and args.xmp_only:
                continue
            if layer == "XMP" and args.info_only:
                continue
            unexpected[k] = v
        if unexpected:
            print(f"{src} -> {dest}: 残存あり")
            for k, v in unexpected.items():
                print(f"   {k} = {v}")
            rc = max(rc, EXIT_REMAINING)
        else:
            print(f"{src} -> {dest}: OK")
    return rc


# ---- set --------------------------------------------------------------------


def _parse_assignment(text: str) -> tuple[str, str]:
    if "=" not in text:
        raise ValueError(f"KEY=VALUE 形式で指定してください: {text!r}")
    k, v = text.split("=", 1)
    k = k.strip()
    if not k:
        raise ValueError(f"キーが空です: {text!r}")
    return k, v


def cmd_set(args: argparse.Namespace) -> int:
    try:
        assignments = [_parse_assignment(a) for a in args.assignments]
    except ValueError as e:
        _err(str(e))
        return EXIT_INPUT
    src = Path(args.file)
    try:
        with PdfDocument(src, args.password) as doc:
            for key, value in assignments:
                if ":" in key or key.startswith("{"):
                    if key in XMP_DATE_KEYS and value:
                        value = dates.user_to_xmp(value)
                    doc.set_xmp(key, value)
                else:
                    if key in DATE_KEYS and value:
                        value = dates.user_to_info(value)
                    doc.set_info(key, value, sync=not args.no_sync)
            dest = _out_path(src, args.output, args.in_place, args.suffix, False)
            doc.save(dest)
    except (DocumentError, dates.DateParseError, KeyError) as e:
        _err(f"{src}: {e}")
        return EXIT_INPUT
    print(f"{src} -> {dest}: OK")
    return EXIT_OK


# ---- parser -----------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="clear-pdf-properties",
        description="PDF のプロパティ（Info 辞書と XMP）を表示・クリア・書き換えます。",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def add_common_io(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("-p", "--password", help="暗号化 PDF のパスワード")
        g = sp.add_mutually_exclusive_group()
        g.add_argument("-o", "--output", help="出力ファイル（単一ファイルのみ）")
        g.add_argument("--in-place", action="store_true", help="元ファイルを上書き")
        sp.add_argument(
            "--suffix", default="_cleaned", help="出力名に付ける接尾辞（既定: _cleaned）"
        )
        sp.add_argument(
            "--no-sync", action="store_true", help="Info の変更を XMP の対応キーに反映しない"
        )

    s = sub.add_parser("show", help="プロパティを表示")
    s.add_argument("files", nargs="+")
    s.add_argument("-p", "--password")
    s.add_argument("--json", action="store_true", help="JSON で出力")
    s.set_defaults(func=cmd_show)

    c = sub.add_parser("clear", help="プロパティをクリア（既定: Info と XMP の両方）")
    c.add_argument("files", nargs="+")
    add_common_io(c)
    mode = c.add_mutually_exclusive_group()
    mode.add_argument("--info-only", action="store_true", help="Info 辞書のみクリア")
    mode.add_argument("--xmp-only", action="store_true", help="XMP のみクリア")
    c.add_argument(
        "--keep",
        help="残すキーをカンマ区切りで指定（例: CreationDate,ModDate,dc:title）",
    )
    c.add_argument("--dry-run", action="store_true", help="保存せず結果だけ表示")
    c.set_defaults(func=cmd_clear)

    st = sub.add_parser(
        "set",
        help="プロパティを設定。KEY=VALUE 形式。XMP は prefix:name。空値はキー削除",
        epilog=(
            f"Info キー: {', '.join(STANDARD_KEYS)}（カスタムキーも可）。"
            "日時は 'YYYY-MM-DD HH:MM:SS +09:00' 形式。"
        ),
    )
    st.add_argument("file")
    st.add_argument("assignments", nargs="+", metavar="KEY=VALUE")
    add_common_io(st)
    st.set_defaults(func=cmd_set)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
