#!/usr/bin/env python3
"""
YouTube Monitor TUI
シンプルなYouTube動画監視とDiscord通知
"""

import json
import asyncio
import logging
import tomllib
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote

import httpx
import pytz

# 設定
CONFIG_FILE = Path("config/settings.toml")
WATCHED_FILE = Path("data/watched_videos.json")
DOWNLOAD_DIR = Path("data/downloads")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class YouTubeMonitor:
    def __init__(self):
        # 必要なディレクトリを作成
        self.ensure_directories()

        self.config = self.load_config()
        self.watched_videos = self.load_watched_videos()
        self.client = httpx.AsyncClient(timeout=30.0)

    def ensure_directories(self):
        """必要なディレクトリを自動作成"""
        directories = [
            CONFIG_FILE.parent,      # config/
            WATCHED_FILE.parent,      # data/
            DOWNLOAD_DIR,             # data/downloads/
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            logger.debug(f"ディレクトリを確認/作成: {directory}")

    def load_config(self) -> dict:
        """設定ファイルを読み込み"""
        with open(CONFIG_FILE, 'rb') as f:
            return tomllib.load(f)

    def load_watched_videos(self) -> dict:
        """既視聴動画を読み込み（メタデータ付き）"""
        if WATCHED_FILE.exists():
            with open(WATCHED_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 古い形式（単純なリスト）から新しい形式への移行
                if isinstance(data, list):
                    logger.info("古い形式のデータを移行中...")
                    return {}
                return data
        return {}

    def save_watched_videos(self):
        """既視聴動画を保存（メタデータ付き）"""
        WATCHED_FILE.parent.mkdir(exist_ok=True)
        with open(WATCHED_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.watched_videos, f, indent=2, ensure_ascii=False)

    async def fetch_playlist_videos(self, playlist_id: str, max_results: int = 50, page_token: Optional[str] = None) -> dict:
        """プレイリストの動画を取得"""
        params = {
            "part": "snippet",
            "playlistId": playlist_id,
            "maxResults": max_results,
            "key": self.config["youtube"]["api_key"]
        }
        if page_token:
            params["pageToken"] = page_token

        response = await self.client.get("https://www.googleapis.com/youtube/v3/playlistItems", params=params)
        response.raise_for_status()
        return response.json()

    async def get_all_playlist_videos(self, playlist_id: str, query: str = "") -> List[dict]:
        """プレイリストの全動画を取得（クエリでフィルタリング）"""
        all_videos = []
        page_token = None

        while True:
            data = await self.fetch_playlist_videos(playlist_id, page_token=page_token)
            items = data.get("items", [])

            for item in items:
                snippet = item["snippet"]
                title = snippet["title"]
                video_id = snippet["resourceId"]["videoId"]
                published_at = snippet["publishedAt"]
                description = snippet.get("description", "")
                thumbnails = snippet.get("thumbnails", {})

                # 高品質なサムネイルを優先
                thumbnail_url = ""
                for quality in ["maxres", "high", "medium", "default"]:
                    if quality in thumbnails:
                        thumbnail_url = thumbnails[quality]["url"]
                        break

                # クエリでフィルタリング
                if query and query not in title:
                    continue

                all_videos.append({
                    "video_id": video_id,
                    "title": title,
                    "description": description,
                    "published_at": published_at,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "thumbnail_url": thumbnail_url,
                    "channel_name": snippet.get("channelTitle", ""),
                    "added_at": datetime.now().isoformat()
                })

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return all_videos

    async def send_discord_notification(self, video: dict, playlist_name: str, max_retries: int = 3):
        """Discordに通知を送信（レート制限対応）"""
        webhook_url = self.config["discord"]["webhook_url"]
        username = self.config["discord"]["username"]

        # URLを生成 - server_urlが設定されている場合は検索URLを使用
        if "server_url" in self.config.get("discord", {}):
            server_url = self.config["discord"]["server_url"].rstrip('/')
            # 動画タイトルから【メンバーシップ限定動画】#XX部分のみを抽出
            match = re.match(r'(【メンバーシップ限定動画】#\d+)', video["title"])
            if match:
                search_query = quote(match.group(1))
            else:
                search_query = quote(video["title"])
            video_url = f"{server_url}?search={search_query}"
        else:
            video_url = video["url"]

        embed = {
            "title": video["title"],
            "url": video_url,
            "color": 0x5865F2,  # Discord blue
            "timestamp": video["published_at"],
            "footer": {"text": f"Playlist: {playlist_name}"}
        }

        # サムネイルがあれば追加
        if video.get("thumbnail_url"):
            embed["image"] = {"url": video["thumbnail_url"]}

        # 説明文があれば追加（短く切り詰める）
        if video.get("description"):
            description = video["description"][:200] + "..." if len(video["description"]) > 200 else video["description"]
            embed["description"] = description

        payload = {
            "username": username,
            "embeds": [embed]
        }

        for attempt in range(max_retries):
            try:
                response = await self.client.post(webhook_url, json=payload)

                if response.status_code == 429:
                    # レート制限時
                    retry_after = int(response.headers.get('Retry-After', 60))
                    logger.warning(f"Discordレート制限。{retry_after}秒待機します... (試行 {attempt + 1}/{max_retries})")
                    await asyncio.sleep(retry_after)
                    continue
                elif response.status_code == 204:
                    # 成功
                    logger.info(f"Discord通知を送信: {video['title']}")
                    return True
                else:
                    # その他エラー
                    response.raise_for_status()

            except httpx.HTTPStatusError as e:
                logger.error(f"Discord通知失敗 (HTTP {e.response.status_code}): {e}")
                if attempt == max_retries - 1:
                    break
                await asyncio.sleep(2 ** attempt)  # 指数バックオフ
            except Exception as e:
                logger.error(f"Discord通知失敗: {e}")
                if attempt == max_retries - 1:
                    break
                await asyncio.sleep(2 ** attempt)

        logger.error(f"Discord通知をあきらめました: {video['title']}")
        return False

    async def download_video_with_ytdlp(self, video_url: str, video_id: str, video_title: str) -> bool:
        """yt-dlpを使用して動画をダウンロード"""
        DOWNLOAD_DIR.mkdir(exist_ok=True)

        # ファイル名に使用できない文字をサニタイズ
        safe_title = re.sub(r'[<>:"/\\|?*]', '_', video_title).strip()

        # 出力テンプレート: data/downloads/タイトル/タイトル.mp4
        output_template = str(DOWNLOAD_DIR / safe_title / f"{safe_title}.mp4")

        cmd = [
            "yt-dlp",
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo[ext=webm]+bestaudio[ext=m4a]/bestvideo[ext=webm]+bestaudio[ext=webm]/best",
            "--output", output_template,
            "--no-playlist",  # プレイリスト全体をダウンロードしない
            "--no-mtime",  # ファイルのタイムスタンプを変更しない
            "--write-thumbnail",  # サムネイルも保存
            "--write-info-json",  # メタデータも保存
            "--embed-metadata",  # メタデータを埋め込み
            "--concurrent-fragments", "4",  # 並列ダウンロード
            "--cookies-from-browser", "firefox",  # ブラウザのクッキーを使用
            video_url
        ]

        try:
            logger.info(f"yt-dlpで動画ダウンロード開始: {video_title}")

            # 非同期でサブプロセスを実行
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                logger.info(f"動画ダウンロード成功: {video_title}")
                return True
            else:
                logger.error(f"動画ダウンロード失敗: {video_title}, エラー: {stderr}")
                return False

        except Exception as e:
            logger.error(f"yt-dlp実行エラー ({video_title}): {e}")
            return False

    def should_poll_now(self) -> bool:
        """現在ポーリングすべき時刻か判定"""
        if not self.config["polling"]["auto_start"]:
            return False

        tz = pytz.timezone(self.config["polling"]["timezone"])
        now = datetime.now(tz)
        weekday = now.strftime("%a").lower()

        for window in self.config["polling"]["windows"]:
            # 曜日チェック
            if weekday not in window["days"]:
                continue

            # 時間チェック
            start_time = datetime.strptime(window["start"], "%H:%M").time()
            end_time = datetime.strptime(window["end"], "%H:%M").time()
            current_time = now.time()

            if start_time <= current_time <= end_time:
                return True

        return False

    async def check_videos(self):
        """動画チェックとダウンロード処理"""
        logger.info("動画チェックを開始...")

        playlists = {p["uid"]: p for p in self.config["youtube"]["playlist_id"]}
        queries = {q["uid"]: q["value"] for q in self.config["youtube"]["query"]}

        total_new_videos = 0
        total_download_attempts = 0

        for uid, playlist in playlists.items():
            query = queries.get(uid, "")
            logger.info(f"チェック中: {playlist['name']} (query: {query})")

            try:
                videos = await self.get_all_playlist_videos(playlist["id"], query)

                # 動画処理ループ
                for video in videos:
                    video_id = video["video_id"]

                    if video_id not in self.watched_videos:
                        # 新しい動画の場合
                        logger.info(f"新しい動画発見: {video['title']}")

                        # Discord通知送信
                        notification_success = await self.send_discord_notification(video, playlist["name"])

                        # yt-dlpで動画ダウンロード
                        download_success = await self.download_video_with_ytdlp(video["url"], video_id, video["title"])
                        total_download_attempts += 1

                        # メタデータ付きで保存（ダウンロード状態を含む）
                        self.watched_videos[video_id] = {
                            "title": video["title"],
                            "description": video.get("description", ""),
                            "published_at": video["published_at"],
                            "url": video["url"],
                            "thumbnail_url": video.get("thumbnail_url", ""),
                            "channel_name": video.get("channel_name", ""),
                            "added_at": video["added_at"],
                            "playlist_name": playlist["name"],
                            "is_downloaded": download_success,
                            "notification_sent": notification_success
                        }
                        total_new_videos += 1

                    else:
                        # 既存動画の場合、ダウンロード状態をチェック
                        watched_data = self.watched_videos[video_id]

                        # 未ダウンロードの動画があればダウンロードを試みる
                        if not watched_data.get("is_downloaded", False):
                            logger.info(f"未ダウンロード動画のダウンロードを試行: {watched_data['title']}")

                            download_success = await self.download_video_with_ytdlp(video["url"], video_id, video["title"])
                            total_download_attempts += 1

                            # ダウンロード状態を更新
                            if download_success:
                                self.watched_videos[video_id]["is_downloaded"] = True
                                logger.info(f"動画ダウンロード成功: {watched_data['title']}")
                            else:
                                logger.warning(f"動画ダウンロード失敗: {watched_data['title']}")

            except Exception as e:
                logger.error(f"動画取得エラー ({playlist['name']}): {e}")

        if total_new_videos > 0 or total_download_attempts > 0:
            self.save_watched_videos()

            if total_new_videos > 0:
                logger.info(f"合計 {total_new_videos} 件の新しい動画を通知しました")

            if total_download_attempts > 0:
                logger.info(f"合計 {total_download_attempts} 件のダウンロード試行がありました")
        else:
            logger.info("新しい動画はありませんでした")

    async def run(self):
        """メインループ"""
        logger.info("YouTube Monitor TUIを起動しました")
        logger.info(f"設定: {len(self.config['youtube']['playlist_id'])} 個のプレイリストを監視")

        try:
            # 起動時に1回だけ強制的に動画チェックを実行
            logger.info("=== 起動時チェックを実行します ===")
            await self.check_videos()
            logger.info("=== 起動時チェック完了 ===")

            while True:
                if self.should_poll_now():
                    logger.info("ポーリングウィンドウ内です - 動画チェックを実行")
                    await self.check_videos()

                    # ウィンドウ内の間隔を取得
                    interval = self.get_window_interval()
                    logger.info(f"次のチェックは {interval // 60} 分後（ウィンドウ内）")
                else:
                    logger.info("ポーリングウィンドウ外です - 次のウィンドウまで待機")
                    interval = self.config["polling"]["default_interval_minutes"] * 60
                    logger.info(f"次のチェックは {interval // 60} 分後（ウィンドウ外）")

                await asyncio.sleep(interval)

        except KeyboardInterrupt:
            logger.info("シャットダウンします...")
        finally:
            await self.client.aclose()

    def get_window_interval(self) -> int:
        """現在のウィンドウに応じた間隔を取得"""
        tz = pytz.timezone(self.config["polling"]["timezone"])
        now = datetime.now(tz)
        weekday = now.strftime("%a").lower()

        for window in self.config["polling"]["windows"]:
            if weekday in window["days"]:
                start_time = datetime.strptime(window["start"], "%H:%M").time()
                end_time = datetime.strptime(window["end"], "%H:%M").time()
                current_time = now.time()

                if start_time <= current_time <= end_time:
                    return window["interval_minutes"] * 60

        return self.config["polling"]["default_interval_minutes"] * 60

    async def test_once(self):
        """テスト実行（一度だけチェック）"""
        logger.info("テスト実行: 一度だけ動画チェックを実行します")
        await self.check_videos()
        await self.client.aclose()


async def main():
    monitor = YouTubeMonitor()

    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        await monitor.test_once()
    else:
        await monitor.run()


def cli_main():
    """CLI用の同期エントリーポイント"""
    asyncio.run(main())


if __name__ == "__main__":
    cli_main()
