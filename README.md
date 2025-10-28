# YouTube Notifier for Discord

ローカルPCでYouTubeチャンネルの新着動画をポーリングし、Discord Webhookへリアルタイム通知するツールです。FastAPI製のダッシュボード(UI+API)とCLIモードの両方を備え、`uv` ベースのモダンなワークフローで開発・運用できます。

## 必要条件

- Python 3.11 以上
- [uv](https://github.com/astral-sh/uv) がインストールされていること

## セットアップ

```bash
# 仮想環境を作成 (任意)
uv venv

# 依存関係をインストール (本番用)
uv pip install -e .

# 開発時: テストツールもまとめて導入
uv pip install -e .[dev]
```

設定ファイルの雛形をコピーし、YouTube Data APIキー・Discord Webhook・監視ウィンドウを編集してください。

```bash
cp config/settings.toml.example config/settings.toml
```

主な設定項目:

- `youtube.api_key`: YouTube Data API v3 のAPIキー
- `youtube.channels`: 監視したいチャンネルIDの配列
- `discord.webhook_url`: 通知先Discord Webhook URL
- `polling.default_interval_minutes`: 通常時ポーリング間隔(分)
- `polling.windows`: 特定時間帯にポーリング間隔を短縮する設定
- `polling.auto_start`: Webサーバー起動時に自動で監視を開始するか

## CLI モード

- 常駐監視: `uv run yt-notifier`
- 単発実行: `uv run yt-notifier --once --log-level DEBUG`

オプション:

- `--config`: 設定ファイルを明示的に指定
- `--log-level`: `DEBUG / INFO / WARNING / ERROR / CRITICAL`

## Webダッシュボードモード

FastAPI + Uvicornで軽量なダッシュボードを提供します。ダウンロード管理・検索・ポーリング制御がブラウザから可能です。

```bash
uv run yt-notifier --web --web-host 0.0.0.0 --web-port 8000
```

- `http://<host>:<port>/` でBootstrapベースのダッシュボードを表示
- WebSocketでダウンロード進捗がリアルタイム更新
- REST API例: `POST /api/polling/start`, `POST /api/videos/search`, `GET /api/downloads`
- APIレスポンスはJSONで返却されるため、他サービスとの連携も容易です

## データ出力

- `config/settings.toml` の `data_dir` 配下に以下が作成されます
  - `state.json`: 最終通知済み動画IDなどの状態
  - `videos/<channel_id>.jsonl`: 永続メタデータログ
  - `videos.db`: SQLite(FTS5)による検索用データベース
  - `downloads/`: `yt-dlp` が保存した動画ファイル

## 運用Tips

- `uv run --with dev pytest` でローカルテストを高速実行
- `uv run yt-notifier --web --log-level DEBUG` でWeb/APIスタックの詳細ログを確認
- Webモードで自動監視を切りたい場合は `polling.auto_start = false` に設定し、`/api/polling/start` を手動呼び出し
- ダウンロードは `yt-dlp>=2025.10.22` を利用し、最新のフォーマット仕様に追従しています

## ライブラリバージョン

- FastAPI `>=0.120.0` (2025年9月リリースの最新安定版)
- Uvicorn `>=0.38.0` のイベントループ制御で高効率な非同期サーバー運用
- httpx `>=0.27.2` によるモダンなHTTPクライアント
- yt-dlp `>=2025.10.22` による最新形式の動画ダウンロード対応

## テスト

```bash
uv run --with dev pytest
```

- `tests/test_scheduler.py`: スケジュール解決ロジック
- `tests/test_state_store.py`: 状態ファイル永続化
- `tests/test_agent.py`: ポーリングエージェントの開始・停止(依存ライブラリ未導入時は自動skip)

## ライセンス

プロジェクトルートの `LICENSE` を参照してください。
