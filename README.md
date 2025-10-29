# YouTube Monitor with Discord Notifications

YouTubeチャンネルの新着動画を監視し、Discordに通知するシンプルなTUIツール。

## 主な機能

- 🎥 **動画監視**: YouTubeプレイリストの新着動画を自動検出
- 💬 **Discord通知**: 新しい動画をDiscordにEmbed形式で通知
- ⏰ **スケジュール実行**: 指定した時間帯のみ監視（ポーリング設定）

## セットアップ

1. **依存関係インストール**:
```bash
uv sync
```

2. **設定ファイル作成**:
```bash
cp config/settings.toml.example config/settings.toml
```

4. **config/settings.tomlを編集**:
```toml
[youtube]
api_key = "YOUR_YOUTUBE_API_KEY"
playlist_id = [
  { uid = 1, id = "PLAYLIST_ID", name = "チャンネル名" }
]
query = [
  { uid = 1, value = "検索キーワード" }
]

[discord]
webhook_url = "YOUR_DISCORD_WEBHOOK_URL"
username = "通知ユーザー名"

[polling]
default_interval_minutes = 240
timezone = "Asia/Tokyo"
auto_start = true
windows = [
  { start = "18:00", end = "22:00", interval_minutes = 5, days = ["tue"] }
]
```

## 使い方

**テスト実行**（一度だけチェック）:
```bash
uv run yt-notifier-discord --test
```

**既存動画のDiscord通知**（古いものから順番に送信）:
```bash
uv run yt-notifier-discord --discord
```

**常時実行**（スケジュール監視）:
```bash
uv run yt-notifier-discord
```

### コマンドラインオプション

- `--test`: テスト実行。一度だけ動画チェックを行い、新着動画があればDiscord通知とダウンロードを実行
- `--discord`: 既存動画のDiscord通知。メタデータにある既存動画を投稿日順（古いものから）にソートし、順番にDiscordに通知
- 引数なし: 常時実行モード。設定したスケジュールに従って定期的に動画監視

## 機能詳細

- Discord通知はレート制限に対応
- YouTube API v3使用
- 非同期処理で高速動作
