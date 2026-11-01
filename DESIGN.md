# clear-pdf-properties 設計書

PDF のプロパティ（メタデータ）を GUI で確認・クリア・書き換えるツール。
Windows ユーザー向けに PyInstaller でビルドした実行ファイルを GitHub Release で配布する。

- 状態: 確定（2026-11-01）
- 決定事項は末尾「7. 決定事項」に集約

---

## 1. 背景と目的

PDF の「プロパティ」は 1 か所ではなく複数の層に分かれて格納されており、
一般的なツールで Info 辞書だけを消しても Acrobat や macOS Preview には XMP 側の値が表示され続ける。
本ツールは Info と XMP の両方を同一画面で扱い、項目単位・一括でのクリアと値の書き換えを可能にする。

## 2. PDF メタデータの構造（前提知識）

| 層 | 格納場所 | 内容 | 備考 |
|---|---|---|---|
| Info 辞書 | trailer `/Info` | Title, Author, Subject, Keywords, Creator, Producer, CreationDate, ModDate、任意のカスタムキー | 古典的な「プロパティ」 |
| XMP | catalog `/Metadata`（XML ストリーム） | 上記の重複 (`dc:`, `xmp:`, `pdf:`) に加え、編集履歴 (`xmpMM:History`)、DocumentID/InstanceID、ツール固有情報 | Acrobat / Preview はこちらを優先表示 |
| 文書 ID | trailer `/ID` | 元ファイル由来のハッシュ | 同一ソースの追跡に使われる |
| 増分更新履歴 | ファイル末尾に追記された旧リビジョン | クリア前の Info/XMP が残存しうる | full rewrite で消える |
| その他 | 注釈 `/T`（作成者）、フォームフィールド、添付ファイル、ページ単位 `/Metadata`、`/PieceInfo` | 個人名・アプリ情報の漏洩源 | v1 では対象外 |

## 3. スコープ

### 3.1 v1 で扱うもの

- Info 辞書の全キー（標準 8 キー＋カスタムキー）の表示・編集・削除
- XMP の全プロパティの表示・編集・削除
- Info と XMP の対応キーの同期（オプション）
- 日時（CreationDate / ModDate / xmp:CreateDate / xmp:ModifyDate / xmp:MetadataDate）の編集・削除
- 保存は常に full rewrite（増分更新履歴を残さない）
- 暗号化 PDF のパスワード入力（所有者パスワードが必要）
- CLI（show / clear / set）。core を共有し、複数ファイル指定によるバッチ処理に対応
- ヘッダに「暗号化の有無」「増分更新の有無」を表示

### 3.2 v1 で扱わないもの

- 注釈作成者、添付ファイル、ページ単位 XMP、`/PieceInfo` の除去
- `/ID` の再生成
- GUI での複数ファイル処理（バッチは CLI で対応）
- コード署名・公証（配布上の制約として README に明記）

## 4. 技術選定

| 項目 | 選定 | 理由 |
|---|---|---|
| 言語 | Python 3.11+ | 要望。PyInstaller 配布前提 |
| PDF 処理 | pikepdf | Info と XMP の両方を扱える。保存が常に full rewrite。Win/mac/Linux の wheel あり |
| GUI | Tkinter (ttk) | 標準ライブラリ。PyInstaller との相性が最も良く、exe が小さい（~20MB）。UI 要件（キー一覧＋ボタン＋折りたたみ）に対して十分 |
| D&D | tkinterdnd2（任意） | ファイルを窓に落として開く。なくても「開く」ボタンで成立 |
| 配布 | PyInstaller `--onefile` + GitHub Actions | タグ push → OS 別ビルド → Release 添付 |
| 品質 | pytest, ruff | core は GUI 非依存にしてテスト対象にする |

### 4.1 不採用案

| 案 | 理由 |
|---|---|
| PySide6 | 見た目は良いが exe が 80MB 超、ビルドトラブルが増える。XMP をツリー表示したくなったら乗り換え候補 |
| Swift + PDFKit | `documentAttributes` は Info のみで XMP 編集は自前実装が必要。Windows 向け要件に合わない |
| qpdf 単体 | XMP 編集が実質不可能 |
| pypdf | XMP の書き込みサポートが弱く、Producer の自動上書き制御も不安定 |

### 4.2 OS サポート

ソースは OS 非依存。バイナリは OS ごとに別ビルドとなる。

| OS | 位置づけ | 制約 |
|---|---|---|
| Windows | 一次ターゲット | コード署名なしのため SmartScreen 警告が出る。回避不可、README に記載 |
| macOS | Release に添付（best effort） | 署名＋公証なしのため Gatekeeper に止められる。`xattr -d com.apple.quarantine` または右クリック→開く の手順と、ソースから `pipx run` する代替を README に記載 |
| Linux | Release に添付（best effort） | glibc 依存のため古いディストリでは動かない可能性。同様にソース実行の代替を記載 |

## 5. 画面設計

```
┌ clear-pdf-properties ──────────────────────────────────────┐
│ [開く]  C:\...\report.pdf          暗号化: なし  増分更新: あり │
├ Info ───────────────────────────────────[Info を全クリア]──┤
│ Title        [Q3 報告書                      ] [クリア]      │
│ Author       [akiyama                        ] [クリア]      │
│ Subject      [                               ] [クリア]      │
│ Keywords     [                               ] [クリア]      │
│ Creator      [Microsoft Word                 ] [クリア]      │
│ Producer     [Microsoft: Print To PDF        ] [クリア]      │
│ CreationDate [2026-10-30 14:02:11 +09:00     ] [クリア]      │
│ ModDate      [2026-10-30 14:02:11 +09:00     ] [クリア]      │
│ (カスタムキー) Company [Kirin...             ] [クリア]      │
├ ▸ XMP (12 項目) ──────────────────────────[XMP を全クリア]──┤
│   展開すると dc:title / dc:creator / xmp:CreateDate /        │
│   xmp:CreatorTool / pdf:Producer / xmpMM:DocumentID /        │
│   xmpMM:History ... を同じ形式で一覧                          │
├────────────────────────────────────────────────────────────┤
│ ☑ Info の編集を XMP の対応キーにも反映      [別名で保存] [上書き] │
└────────────────────────────────────────────────────────────┘
```

### 5.1 Info セクション

- 標準 8 キーは値が存在しなくても常に行を表示（空欄＝キーなし）
- カスタムキーは存在するものだけ表示
- 各行：キー名 / 編集可能な値フィールド / [クリア] ボタン
- [Info を全クリア]：Info 辞書の全キーを削除

### 5.2 XMP セクション

- 既定は折りたたみ。見出しに項目数を表示
- 展開時は Info と同じ形式（プロパティ名 / 値 / [クリア]）で一覧
- 配列・構造体プロパティ（`dc:creator` の Seq、`xmpMM:History` など）は文字列化して表示し、編集は削除のみ可（値編集は v2）
- [XMP を全クリア]：`/Metadata` ストリーム自体を削除（空の XMP パケットを残さない）

### 5.3 操作の意味

- **クリア** = キー自体を削除する。空文字を残さない（空文字は「Author: (空)」として残り、ツールによっては表示される）
- **値の編集** = フィールドに直接入力。保存時に反映
- クリア・編集はメモリ上の状態のみ変更し、保存ボタンでファイルに書き出す

### 5.4 Info ↔ XMP 同期

| Info | XMP |
|---|---|
| Title | `dc:title` |
| Author | `dc:creator` |
| Subject | `dc:description` |
| Keywords | `pdf:Keywords`（`dc:subject` も対象） |
| Creator | `xmp:CreatorTool` |
| Producer | `pdf:Producer` |
| CreationDate | `xmp:CreateDate` |
| ModDate | `xmp:ModifyDate`（`xmp:MetadataDate` も対象） |

- 同期チェック ON のとき、Info 側の編集・クリアは対応する XMP キーにも同じ操作を適用する
- XMP 側の操作は Info に波及させない（XMP にしかないキーが大半のため非対称でよい）
- OFF のときは完全に独立

### 5.5 日時

- 表示・入力形式：`YYYY-MM-DD HH:MM:SS +09:00`（タイムゾーン省略時はローカル）
- 保存時に Info 形式 `D:20261030140211+09'00'` と XMP 形式 ISO 8601 の両方へ変換
- 不正な入力は保存前にバリデーションし、該当行をハイライトして保存を中断

### 5.6 保存

- [別名で保存]：既定。ファイル名に `_cleaned` を付けた名前を初期提案
- [上書き]：確認ダイアログを挟む
- 保存は常に full rewrite（pikepdf の既定動作）
- pikepdf が XMP に自身を editor として書き込む挙動（`set_pikepdf_as_editor`）を無効化し、Producer はユーザーの設定値または削除状態を保持する
- 保存後にファイルを再読込して画面を更新し、残存キーを目視確認できるようにする

### 5.7 暗号化 PDF

- 開く時にパスワード入力ダイアログを表示
- 所有者パスワードでない場合は編集不可である旨を表示し、閲覧のみ許可


### 5.8 CLI

```
clear-pdf-properties show  <in.pdf>...
clear-pdf-properties clear <in.pdf>... [-o out.pdf | --in-place] [--info-only | --xmp-only] [--keep KEY,...]
clear-pdf-properties set   <in.pdf>    [-o out.pdf | --in-place] Title="..." Author="..." CreationDate="2026-10-30 14:02:11 +09:00"
```

- `show`：Info / XMP / 暗号化 / 増分更新の有無をテキストまたは `--json` で出力
- `clear`：既定は Info と XMP の両方。複数ファイル指定時は `--in-place` か `--suffix _cleaned` で出力名を決める
- `set`：GUI と同じ同期ルール（`--no-sync` で解除）、同じ日時フォーマット
- 終了コード：0 成功 / 1 入力エラー / 2 保存後の検証で残存キーあり
- 引数なしで起動した場合は GUI を開く（exe ダブルクリック対応）

## 6. 構成

```
clear-pdf-properties/
├ src/clear_pdf_properties/
│  ├ core/              # pikepdf ラッパ。GUI 非依存、pytest 対象
│  │  ├ document.py     # open / save / 暗号化判定 / 増分更新判定
│  │  ├ info.py         # Info 辞書の read / set / delete
│  │  ├ xmp.py          # XMP の read / set / delete、Info との対応表
│  │  └ dates.py        # 日時の相互変換とバリデーション
│  ├ gui/
│  │  └ app.py          # Tkinter
│  ├ cli.py             # argparse。show / clear / set
│  └ __main__.py        # 引数なし → GUI、引数あり → CLI
├ tests/                # フィクスチャ PDF はテスト内で生成（バイナリをリポジトリに置かない）
├ pyproject.toml
├ build/app.spec        # PyInstaller
├ .github/workflows/
│  ├ ci.yml             # push/PR: ruff + pytest（3 OS）
│  └ release.yml        # v* タグ: PyInstaller → Release 添付
├ DESIGN.md
└ README.md
```

### 6.1 core の責務分離

- `document.py`：ファイルの開閉のみ。Info/XMP の操作は持たない
- `info.py` / `xmp.py`：それぞれの層に閉じた read / set / delete
- 同期ロジックは `xmp.py` の対応表を参照して GUI 層・CLI 層が呼び分ける
- GUI / CLI は core の関数を呼ぶだけで、pikepdf を直接 import しない

### 6.2 テスト方針

- テスト内で pikepdf を使って Info / XMP / 増分更新ありの PDF を生成し、操作後の結果を検証
- 「クリア後に再読込してキーが存在しない」ことを必ず確認
- 日時変換は往復（parse → format → parse）の同一性を検証

### 6.3 リリースフロー

1. `v*` タグを push
2. GitHub Actions が Windows / macOS / Linux で PyInstaller ビルド
3. 生成物を Release に添付（`clear-pdf-properties-<version>-<os>.zip`）
4. README に SmartScreen / Gatekeeper の注意を記載

## 7. 決定事項

| # | 項目 | 決定 | 日付 |
|---|---|---|---|
| 1 | GUI フレームワーク | Tkinter（見た目より配布の確実さを優先） | 2026-11-01 |
| 2 | 「Info の編集を XMP に反映」の既定値 | ON | 2026-11-01 |
| 3 | Release に含めるバイナリ | Windows / macOS / Linux。mac・Linux は best effort と README に明記 | 2026-11-01 |
| 4 | CLI | v1 に含める（show / clear / set） | 2026-11-01 |
