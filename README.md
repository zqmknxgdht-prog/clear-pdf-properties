# clear-pdf-properties

PDF のプロパティ（メタデータ）を確認・クリア・書き換えるツールです。GUI と CLI の両方があります。

PDF のプロパティは **Info 辞書** と **XMP** の 2 か所に入っており、Info だけ消しても Acrobat や macOS プレビューには XMP 側の値が表示され続けます。このツールは両方を同じ画面で扱い、保存時は常にファイル全体を書き直すので、過去の編集履歴（増分更新）も残りません。

## ダウンロード

[Releases](../../releases) から OS に合ったものを取得してください。

| OS | ファイル | 備考 |
|---|---|---|
| Windows | `clear-pdf-properties-vX.Y.Z-windows-x64.zip` | `clear-pdf-properties.exe`（GUI）と `clear-pdf-properties-cli.exe`（CLI） |
| macOS | `...-macos-arm64.tar.gz` | Apple Silicon のみ、best effort。下記の Gatekeeper 注意を参照。Intel Mac はソースから実行 |
| Linux | `...-linux-x64.tar.gz` | best effort。glibc 依存のため古い環境では動かないことがあります |

### Windows の SmartScreen 警告について

実行ファイルはコード署名していないため、初回起動時に「Windows によって PC が保護されました」と表示されます。
「詳細情報」→「実行」で起動できます。心配な場合はソースから実行してください（下記）。

### macOS の Gatekeeper について

署名・公証していないため、そのままでは起動がブロックされます。ターミナルで

```
xattr -d com.apple.quarantine ./clear-pdf-properties
```

を実行するか、Finder で右クリック →「開く」を選んでください。
または Python があればソースから実行する方が確実です。

## ソースから実行

Python 3.10 以上が必要です。

```
pipx install git+https://github.com/zqmknxgdht-prog/clear-pdf-properties
clear-pdf-properties            # GUI
clear-pdf-properties show a.pdf # CLI
```

開発用：

```
git clone https://github.com/zqmknxgdht-prog/clear-pdf-properties
cd clear-pdf-properties
pip install -e ".[dev]"
pytest
python -m clear_pdf_properties
```

## GUI

- 「開く」または PDF をドロップ（ドロップは `tkinterdnd2` がある場合のみ）
- **Info** セクション：標準 8 項目＋カスタムキー。値を直接編集でき、「クリア」でキー自体を削除
- **XMP** セクション：折りたたみ。展開すると全プロパティを一覧。単純値は編集可、配列・構造体は削除のみ
- 「Info を全クリア」「XMP を全クリア」で各層を一括削除
- 「Info の編集を XMP の対応キーにも反映」（既定 ON）：Title → dc:title、Author → dc:creator などに同じ操作を適用
- 日時は `YYYY-MM-DD HH:MM:SS +09:00` 形式で表示・入力（タイムゾーン省略時はローカル）
- 「別名で保存」が既定（`_cleaned.pdf` を提案）。「上書き保存」は確認あり
- 保存後は書き出したファイルを再読込して表示するので、残った項目を確認できます
- 暗号化 PDF は所有者パスワードが必要。保存後も同じ暗号化が維持されます

## CLI

```
clear-pdf-properties show  a.pdf b.pdf [--json]
clear-pdf-properties clear a.pdf [-o out.pdf | --in-place] [--info-only | --xmp-only]
                                 [--keep CreationDate,ModDate] [--dry-run]
clear-pdf-properties clear *.pdf --in-place          # バッチ
clear-pdf-properties set   a.pdf Title="報告書" Author= "CreationDate=2026-10-30 14:02:11 +09:00"
clear-pdf-properties set   a.pdf xmp:CreatorTool=Tool --no-sync
```

- `set` の空値（`Author=`）はキー削除
- XMP キーは `prefix:name`（dc, xmp, xmpMM, pdf, pdfaid, photoshop など）
- 終了コード：`0` 成功 / `1` 入力エラー / `2` 保存後の検証でプロパティが残っていた

## 扱わないもの（v1）

注釈の作成者、添付ファイル、ページ単位の XMP、`/PieceInfo`、文書 ID（`/ID`）の再生成。
本文中の個人情報には一切触れません。

設計の詳細は [DESIGN.md](DESIGN.md) を参照してください。

## ライセンス

MIT
