"""Tkinter GUI for viewing, clearing and editing PDF properties."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .. import __version__
from ..core import (
    DATE_KEYS,
    STANDARD_KEYS,
    XMP_DATE_KEYS,
    DocumentError,
    NotEditable,
    PasswordRequired,
    PdfDocument,
    XmpProperty,
    dates,
)

APP_TITLE = "clear-pdf-properties"
ENTRY_WIDTH = 60


def _display_info_value(key: str, value: str) -> str:
    if key in DATE_KEYS:
        try:
            return dates.info_to_user(value)
        except dates.DateParseError:
            return value
    return value


def _display_xmp_value(key: str, value: str) -> str:
    if key in XMP_DATE_KEYS:
        try:
            return dates.xmp_to_user(value)
        except dates.DateParseError:
            return value
    return value


@dataclass
class Row:
    key: str
    var: tk.StringVar
    original: str  # display-form value when the row was built
    entry: ttk.Entry
    clear_btn: ttk.Button
    clark: str = ""  # XMP only
    simple: bool = True


class ScrollFrame(ttk.Frame):
    """A frame inside a vertical-scrolling canvas."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vbar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.bind_all(seq, self._on_wheel, add="+")

    def _on_inner(self, _e: tk.Event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, e: tk.Event) -> None:
        self.canvas.itemconfigure(self._win, width=e.width)

    def _on_wheel(self, e: tk.Event) -> None:
        if getattr(e, "num", None) == 4:
            self.canvas.yview_scroll(-1, "units")
        elif getattr(e, "num", None) == 5:
            self.canvas.yview_scroll(1, "units")
        else:
            delta = -1 if e.delta > 0 else 1
            self.canvas.yview_scroll(delta, "units")


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"{APP_TITLE} {__version__}")
        self.root.geometry("820x640")
        self.root.minsize(640, 400)

        self.doc: PdfDocument | None = None
        self.password: str | None = None
        self.info_rows: dict[str, Row] = {}
        self.xmp_rows: list[Row] = []
        self.xmp_expanded = tk.BooleanVar(value=False)
        self.sync_var = tk.BooleanVar(value=True)

        self._build()
        self._set_enabled(False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._setup_dnd()

    # ---- building ----------------------------------------------------------

    def _build(self) -> None:
        top = ttk.Frame(self.root, padding=(8, 8, 8, 4))
        top.pack(fill="x")
        ttk.Button(top, text="開く...", command=self.open_dialog).pack(side="left")
        self.path_var = tk.StringVar(value="PDF をここにドロップするか「開く」を押してください")
        ttk.Label(top, textvariable=self.path_var, anchor="w").pack(
            side="left", fill="x", expand=True, padx=8
        )
        self.status_var = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.status_var, anchor="e").pack(side="right")

        self.scroll = ScrollFrame(self.root)
        self.scroll.pack(fill="both", expand=True, padx=8)
        body = self.scroll.inner

        # Info section
        info_head = ttk.Frame(body)
        info_head.pack(fill="x", pady=(6, 2))
        ttk.Label(info_head, text="Info", font=("", 11, "bold")).pack(side="left")
        self.info_clear_all_btn = ttk.Button(
            info_head, text="Info を全クリア", command=self.clear_all_info
        )
        self.info_clear_all_btn.pack(side="right")
        self.info_frame = ttk.Frame(body)
        self.info_frame.pack(fill="x")
        self.info_frame.columnconfigure(1, weight=1)

        # XMP section
        xmp_head = ttk.Frame(body)
        xmp_head.pack(fill="x", pady=(12, 2))
        self.xmp_toggle_btn = ttk.Button(xmp_head, text="▸ XMP", command=self.toggle_xmp, width=18)
        self.xmp_toggle_btn.pack(side="left")
        self.xmp_clear_all_btn = ttk.Button(
            xmp_head, text="XMP を全クリア", command=self.clear_all_xmp
        )
        self.xmp_clear_all_btn.pack(side="right")
        self.xmp_frame = ttk.Frame(body)
        self.xmp_frame.columnconfigure(1, weight=1)
        # packed/unpacked by toggle_xmp

        # Bottom bar
        bottom = ttk.Frame(self.root, padding=8)
        bottom.pack(fill="x")
        self.sync_check = ttk.Checkbutton(
            bottom, text="Info の編集を XMP の対応キーにも反映", variable=self.sync_var
        )
        self.sync_check.pack(side="left")
        self.overwrite_btn = ttk.Button(bottom, text="上書き保存", command=self.save_overwrite)
        self.overwrite_btn.pack(side="right")
        self.save_as_btn = ttk.Button(bottom, text="別名で保存...", command=self.save_as)
        self.save_as_btn.pack(side="right", padx=(0, 6))

    def _setup_dnd(self) -> None:
        try:
            from tkinterdnd2 import DND_FILES  # type: ignore[import-not-found]
        except Exception:
            return
        try:
            self.root.drop_target_register(DND_FILES)  # type: ignore[attr-defined]
            self.root.dnd_bind("<<Drop>>", self._on_drop)  # type: ignore[attr-defined]
        except Exception:
            return

    def _on_drop(self, event: tk.Event) -> None:
        data = getattr(event, "data", "")
        files = self.root.tk.splitlist(data)
        if files:
            self.open_file(files[0])

    # ---- row helpers -------------------------------------------------------

    def _make_row(
        self,
        parent: ttk.Frame,
        r: int,
        key: str,
        value: str,
        on_clear,
        *,
        editable: bool = True,
        clark: str = "",
        simple: bool = True,
    ) -> Row:
        ttk.Label(parent, text=key, width=22, anchor="w").grid(
            row=r, column=0, sticky="w", padx=(0, 6), pady=1
        )
        var = tk.StringVar(value=value)
        entry = ttk.Entry(parent, textvariable=var, width=ENTRY_WIDTH)
        entry.grid(row=r, column=1, sticky="ew", pady=1)
        if not editable:
            entry.state(["readonly"])
        btn = ttk.Button(parent, text="クリア", width=6, command=on_clear)
        btn.grid(row=r, column=2, padx=(6, 0), pady=1)
        return Row(key, var, value, entry, btn, clark, simple)

    def _rebuild_rows(self) -> None:
        for w in self.info_frame.winfo_children():
            w.destroy()
        for w in self.xmp_frame.winfo_children():
            w.destroy()
        self.info_rows.clear()
        self.xmp_rows.clear()
        if self.doc is None:
            self.xmp_toggle_btn.configure(text="▸ XMP")
            return

        info = self.doc.info
        keys = list(STANDARD_KEYS) + [k for k in info if k not in STANDARD_KEYS]
        for r, key in enumerate(keys):
            raw = info.get(key, "")
            shown = _display_info_value(key, raw) if raw else ""
            row = self._make_row(
                self.info_frame, r, key, shown, lambda k=key: self.clear_info_key(k)
            )
            self.info_rows[key] = row

        props = self.doc.xmp
        for r, p in enumerate(props):
            shown = _display_xmp_value(p.key, p.value) if p.simple else p.value
            row = self._make_row(
                self.xmp_frame,
                r,
                p.key,
                shown,
                lambda pr=p: self.clear_xmp_prop(pr),
                editable=p.simple and bool(p.clark),
                clark=p.clark,
                simple=p.simple,
            )
            self.xmp_rows.append(row)
        if not props:
            ttk.Label(self.xmp_frame, text="(XMP なし)", foreground="gray").grid(
                row=0, column=0, sticky="w"
            )
        arrow = "▾" if self.xmp_expanded.get() else "▸"
        self.xmp_toggle_btn.configure(text=f"{arrow} XMP ({len(props)} 項目)")
        self._apply_xmp_visibility()
        self._update_status()

    def _apply_xmp_visibility(self) -> None:
        if self.xmp_expanded.get():
            self.xmp_frame.pack(fill="x")
        else:
            self.xmp_frame.pack_forget()

    def toggle_xmp(self) -> None:
        self.xmp_expanded.set(not self.xmp_expanded.get())
        arrow = "▾" if self.xmp_expanded.get() else "▸"
        n = len(self.xmp_rows)
        self.xmp_toggle_btn.configure(
            text=f"{arrow} XMP ({n} 項目)" if self.doc else f"{arrow} XMP"
        )
        self._apply_xmp_visibility()

    def _set_enabled(self, enabled: bool) -> None:
        state = ["!disabled"] if enabled else ["disabled"]
        for w in (
            self.info_clear_all_btn,
            self.xmp_clear_all_btn,
            self.save_as_btn,
            self.overwrite_btn,
            self.sync_check,
        ):
            w.state(state)

    def _update_status(self) -> None:
        if self.doc is None:
            self.status_var.set("")
            return
        enc = "あり" if self.doc.encrypted else "なし"
        inc = "あり" if self.doc.incremental_updates else "なし"
        edit = "" if self.doc.editable else "  [閲覧のみ]"
        self.status_var.set(f"暗号化: {enc}   増分更新: {inc}{edit}")

    # ---- opening -------------------------------------------------------------

    def open_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="PDF を開く", filetypes=[("PDF", "*.pdf"), ("すべて", "*.*")]
        )
        if path:
            self.open_file(path)

    def open_file(self, path: str) -> None:
        if not self._confirm_discard():
            return
        password: str | None = None
        while True:
            try:
                doc = PdfDocument(path, password)
                break
            except PasswordRequired:
                password = simpledialog.askstring(
                    "パスワード",
                    "この PDF は暗号化されています。パスワードを入力してください:",
                    show="*",
                    parent=self.root,
                )
                if password is None:
                    return
            except DocumentError as e:
                messagebox.showerror("開けません", str(e), parent=self.root)
                return
        if self.doc is not None:
            self.doc.close()
        self.doc = doc
        self.password = password
        self.path_var.set(str(doc.path))
        self._rebuild_rows()
        self._set_enabled(doc.editable)
        if not doc.editable:
            messagebox.showwarning(
                "閲覧のみ",
                "所有者パスワードではないため、この PDF のプロパティは変更できません。",
                parent=self.root,
            )

    # ---- dirty tracking ------------------------------------------------------

    def _has_pending_edits(self) -> bool:
        for row in self.info_rows.values():
            if row.var.get() != row.original:
                return True
        for row in self.xmp_rows:
            if row.simple and row.var.get() != row.original:
                return True
        return False

    def _is_dirty(self) -> bool:
        return self.doc is not None and (self.doc.dirty or self._has_pending_edits())

    def _confirm_discard(self) -> bool:
        if not self._is_dirty():
            return True
        return messagebox.askyesno(
            "未保存の変更", "保存していない変更があります。破棄しますか？", parent=self.root
        )

    def _on_close(self) -> None:
        if self._confirm_discard():
            if self.doc is not None:
                self.doc.close()
            self.root.destroy()

    # ---- clearing ------------------------------------------------------------

    def clear_info_key(self, key: str) -> None:
        if self.doc is None:
            return
        try:
            self.doc.delete_info(key, sync=self.sync_var.get())
        except NotEditable as e:
            messagebox.showerror("編集不可", str(e), parent=self.root)
            return
        self._rebuild_rows()

    def clear_all_info(self) -> None:
        if self.doc is None:
            return
        self.doc.clear_info(sync=self.sync_var.get())
        self._rebuild_rows()

    def clear_xmp_prop(self, prop: XmpProperty) -> None:
        if self.doc is None or not prop.clark:
            return
        self.doc.delete_xmp(prop.clark)
        self._rebuild_rows()

    def clear_all_xmp(self) -> None:
        if self.doc is None:
            return
        self.doc.clear_xmp()
        self._rebuild_rows()

    # ---- saving --------------------------------------------------------------

    def _apply_pending_edits(self) -> bool:
        """Push edited field values into the document. Returns False on validation error."""
        assert self.doc is not None
        bad: list[Row] = []
        sync = self.sync_var.get()
        for row in self.info_rows.values():
            text = row.var.get().strip()
            if text == row.original:
                continue
            value = text
            if row.key in DATE_KEYS and text:
                try:
                    value = dates.user_to_info(text)
                except dates.DateParseError:
                    bad.append(row)
                    continue
            self.doc.set_info(row.key, value, sync=sync)
        for row in self.xmp_rows:
            if not row.simple or not row.clark:
                continue
            text = row.var.get().strip()
            if text == row.original:
                continue
            value = text
            if row.key in XMP_DATE_KEYS and text:
                try:
                    value = dates.user_to_xmp(text)
                except dates.DateParseError:
                    bad.append(row)
                    continue
            self.doc.set_xmp(row.clark, value)
        for row in list(self.info_rows.values()) + self.xmp_rows:
            row.entry.configure(style="TEntry")
        if bad:
            style = ttk.Style()
            style.configure("Bad.TEntry", fieldbackground="#ffd6d6")
            for row in bad:
                row.entry.configure(style="Bad.TEntry")
            messagebox.showerror(
                "日時の形式が不正です",
                "赤く表示された項目の日時を次の形式で入力してください:\nYYYY-MM-DD HH:MM:SS +09:00",
                parent=self.root,
            )
            return False
        return True

    def _save_to(self, target: Path | None) -> None:
        assert self.doc is not None
        if not self._apply_pending_edits():
            return
        try:
            written = self.doc.save(target)
        except (DocumentError, OSError) as e:
            messagebox.showerror("保存に失敗しました", str(e), parent=self.root)
            return
        # Reopen the written file so the view reflects what is actually on disk.
        self.doc.close()
        try:
            self.doc = PdfDocument(written, self.password)
        except DocumentError as e:
            messagebox.showerror("再読込に失敗しました", str(e), parent=self.root)
            self.doc = None
            self._set_enabled(False)
            self._rebuild_rows()
            return
        self.path_var.set(str(written))
        self._rebuild_rows()
        remaining = len(self.doc.info) + len(self.doc.xmp)
        messagebox.showinfo(
            "保存しました",
            f"{written}\n\n残っているプロパティ: {remaining} 項目",
            parent=self.root,
        )

    def save_as(self) -> None:
        if self.doc is None:
            return
        src = self.doc.path
        path = filedialog.asksaveasfilename(
            title="別名で保存",
            defaultextension=".pdf",
            initialdir=str(src.parent),
            initialfile=f"{src.stem}_cleaned.pdf",
            filetypes=[("PDF", "*.pdf")],
        )
        if path:
            self._save_to(Path(path))

    def save_overwrite(self) -> None:
        if self.doc is None:
            return
        if not messagebox.askyesno(
            "上書き保存",
            f"{self.doc.path}\n\nを上書きします。元に戻せません。よろしいですか？",
            parent=self.root,
        ):
            return
        self._save_to(None)


def run(argv: list[str] | None = None) -> int:
    try:
        from tkinterdnd2 import TkinterDnD  # type: ignore[import-not-found]

        root = TkinterDnD.Tk()
    except Exception:
        root = tk.Tk()
    app = App(root)
    if argv:
        root.after(100, lambda: app.open_file(argv[0]))
    root.mainloop()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run())
