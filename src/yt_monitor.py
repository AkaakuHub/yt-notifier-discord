#!/usr/bin/env python3
"""
YouTube Monitor TUI
シンプルなYouTube動画監視とDiscord通知
"""

import json
import asyncio
import logging
import tomllib
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import httpx
import pytz

# 設定
CONFIG_FILE = Path("config/settings.toml")
WATCHED_FILE = Path("data/watched_videos.json")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class YouTubeMonitor:
    def __init__(self):
        self.config = self.load_config()
        self.watched_videos = self.load_watched_videos()
        self.client = httpx.AsyncClient(timeout=30.0)

    def load_config(self) -> dict:
        """設定ファイルを読み込み"""
        with open(CONFIG_FILE, 'rb') as f:
            return tomllib.load(f)

    def load_watched_videos(self) -> dict:
        """既視聴動画を読み込み（メタデータ付き）"""
        if WATCHED_FILE.exists():
            with open(WATCHED_FILE, 'r') as f:
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
        with open(WATCHED_FILE, 'w') as f:
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

    async def send_discord_notification(self, video: dict, playlist_name: str):
        """Discordに通知を送信"""
        webhook_url = self.config["discord"]["webhook_url"]
        username = self.config["discord"]["username"]

        embed = {
            "title": video["title"],
            "url": video["url"],
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

        try:
            response = await self.client.post(webhook_url, json=payload)
            response.raise_for_status()
            logger.info(f"Discord通知を送信: {video['title']}")
        except Exception as e:
            logger.error(f"Discord通知失敗: {e}")

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
        """新しい動画をチェック"""
        logger.info("動画チェックを開始...")

        playlists = {p["uid"]: p for p in self.config["youtube"]["playlist_id"]}
        queries = {q["uid"]: q["value"] for q in self.config["youtube"]["query"]}

        total_new_videos = 0

        for uid, playlist in playlists.items():
            query = queries.get(uid, "")
            logger.info(f"チェック中: {playlist['name']} (query: {query})")

            try:
                videos = await self.get_all_playlist_videos(playlist["id"], query)

                # 新しい動画を探す
                for video in videos:
                    if video["video_id"] not in self.watched_videos:
                        logger.info(f"新しい動画発見: {video['title']}")
                        await self.send_discord_notification(video, playlist["name"])

                        # メタデータ付きで保存
                        self.watched_videos[video["video_id"]] = {
                            "title": video["title"],
                            "description": video.get("description", ""),
                            "published_at": video["published_at"],
                            "url": video["url"],
                            "thumbnail_url": video.get("thumbnail_url", ""),
                            "channel_name": video.get("channel_name", ""),
                            "added_at": video["added_at"],
                            "playlist_name": playlist["name"]
                        }
                        total_new_videos += 1

            except Exception as e:
                logger.error(f"動画取得エラー ({playlist['name']}): {e}")

        if total_new_videos > 0:
            self.save_watched_videos()
            logger.info(f"合計 {total_new_videos} 件の新しい動画を通知しました")
        else:
            logger.info("新しい動画はありませんでした")

    async def run(self):
        """メインループ"""
        logger.info("YouTube Monitor TUIを起動しました")
        logger.info(f"設定: {len(self.config['youtube']['playlist_id'])} 個のプレイリストを監視")

        try:
            while True:
                if self.should_poll_now():
                    await self.check_videos()

                # 次のチェックまで待機
                interval = self.config["polling"]["default_interval_minutes"] * 60
                logger.info(f"次のチェックは {interval // 60} 分後")
                await asyncio.sleep(interval)

        except KeyboardInterrupt:
            logger.info("シャットダウンします...")
        finally:
            await self.client.aclose()

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


if __name__ == "__main__":
    asyncio.run(main())
