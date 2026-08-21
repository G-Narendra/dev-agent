"""
Messaging integration for Slack, Telegram, Discord.

Like Cline's connect system:
- Chat with your agent from messaging platforms
- Each conversation thread maps to an agent session
- Supports multiple platforms
"""
from __future__ import annotations
import os
import json
import asyncio
from dataclasses import dataclass, field
from typing import Optional, Callable, Any
from datetime import datetime
from enum import Enum


class Platform(str, Enum):
    TELEGRAM = "telegram"
    SLACK = "slack"
    DISCORD = "discord"


@dataclass
class Message:
    """A message from a messaging platform."""
    platform: Platform
    channel_id: str
    user_id: str
    text: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    thread_id: Optional[str] = None  # For threaded conversations


@dataclass
class BotConfig:
    """Configuration for a messaging bot."""
    platform: Platform
    token: str
    enabled: bool = True
    workspace: str = "."
    approval_required: bool = True  # Require approval for file edits
    allowed_users: list = field(default_factory=list)  # Empty = all users


class TelegramBot:
    """Telegram bot integration."""
    
    def __init__(self, token: str, workspace: str = "."):
        self.token = token
        self.workspace = workspace
        self._running = False
        self._on_message: Optional[Callable] = None

    async def start(self, on_message: Callable = None):
        """Start the Telegram bot."""
        self._on_message = on_message
        self._running = True
        
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                # Get bot info
                resp = await client.get(f"https://api.telegram.org/bot{self.token}/getMe")
                if resp.status_code == 200:
                    bot_info = resp.json().get("result", {})
                    print(f"Telegram bot started: @{bot_info.get('username', 'unknown')}")
                
                # Poll for messages
                offset = 0
                while self._running:
                    resp = await client.get(
                        f"https://api.telegram.org/bot{self.token}/getUpdates",
                        params={"offset": offset, "timeout": 30}
                    )
                    if resp.status_code == 200:
                        updates = resp.json().get("result", [])
                        for update in updates:
                            offset = update["update_id"] + 1
                            if "message" in update:
                                msg = update["message"]
                                message = Message(
                                    platform=Platform.TELEGRAM,
                                    channel_id=str(msg["chat"]["id"]),
                                    user_id=str(msg["from"]["id"]),
                                    text=msg.get("text", ""),
                                    thread_id=str(msg.get("message_thread_id", "")),
                                )
                                if self._on_message:
                                    response = await self._on_message(message)
                                    if response:
                                        await self._send_message(message.channel_id, response, message.thread_id)
        except ImportError:
            print("httpx required for Telegram bot. Install with: pip install httpx")
        except Exception as e:
            print(f"Telegram bot error: {e}")

    async def _send_message(self, chat_id: str, text: str, thread_id: str = None):
        """Send a message to Telegram."""
        import httpx
        async with httpx.AsyncClient() as client:
            params = {"chat_id": chat_id, "text": text}
            if thread_id:
                params["message_thread_id"] = thread_id
            await client.post(f"https://api.telegram.org/bot{self.token}/sendMessage", json=params)

    def stop(self):
        """Stop the bot."""
        self._running = False


class SlackBot:
    """Slack bot integration."""
    
    def __init__(self, bot_token: str, workspace: str = "."):
        self.bot_token = bot_token
        self.workspace = workspace
        self._running = False
        self._on_message: Optional[Callable] = None

    async def start(self, on_message: Callable = None):
        """Start the Slack bot using Socket Mode."""
        self._on_message = on_message
        self._running = True
        
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                # Test connection
                resp = await client.get(
                    "https://slack.com/api/auth.test",
                    headers={"Authorization": f"Bearer {self.bot_token}"}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("ok"):
                        print(f"Slack bot connected as: {data.get('user', 'unknown')}")
                    else:
                        print(f"Slack auth failed: {data.get('error')}")
                        return
                
                # Listen via RTM (simplified)
                resp = await client.post(
                    "https://slack.com/api/rtm.connect",
                    headers={"Authorization": f"Bearer {self.bot_token}"}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("ok"):
                        ws_url = data.get("url")
                        if ws_url:
                            await self._listen_ws(ws_url)
        except ImportError:
            print("httpx required for Slack bot.")
        except Exception as e:
            print(f"Slack bot error: {e}")

    async def _listen_ws(self, ws_url: str):
        """Listen for WebSocket messages (simplified polling fallback)."""
        # In production, use websockets library for real WS connection
        pass

    async def _send_message(self, channel: str, text: str, thread_ts: str = None):
        """Send a message to Slack."""
        import httpx
        async with httpx.AsyncClient() as client:
            payload = {"channel": channel, "text": text}
            if thread_ts:
                payload["thread_ts"] = thread_ts
            await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {self.bot_token}"},
                json=payload
            )

    def stop(self):
        """Stop the bot."""
        self._running = False


class DiscordBot:
    """Discord bot integration."""
    
    def __init__(self, token: str, workspace: str = "."):
        self.token = token
        self.workspace = workspace
        self._running = False
        self._on_message: Optional[Callable] = None

    async def start(self, on_message: Callable = None):
        """Start the Discord bot."""
        self._on_message = on_message
        self._running = True
        
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                # Test connection
                resp = await client.get(
                    "https://discord.com/api/v10/users/@me",
                    headers={"Authorization": f"Bot {self.token}"}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    print(f"Discord bot connected as: {data.get('username', 'unknown')}")
                else:
                    print(f"Discord auth failed: {resp.status_code}")
                    return
        except ImportError:
            print("httpx required for Discord bot.")
        except Exception as e:
            print(f"Discord bot error: {e}")

    def stop(self):
        """Stop the bot."""
        self._running = False


class MessagingManager:
    """Manages all messaging platform connections."""
    
    def __init__(self, project_root: str = "."):
        self.project_root = os.path.abspath(project_root)
        self.bots: dict[str, Any] = {}
        self._config_path = os.path.join(self.project_root, ".dev", "messaging.json")
        self._load_config()

    def _load_config(self):
        """Load messaging configuration."""
        if os.path.exists(self._config_path):
            with open(self._config_path) as f:
                data = json.load(f)
            for platform, config in data.items():
                if config.get("enabled"):
                    self.add_bot(
                        Platform(platform),
                        token=config["token"],
                        workspace=config.get("workspace", self.project_root),
                    )

    def _save_config(self):
        """Save messaging configuration."""
        os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
        data = {}
        for key, bot in self.bots.items():
            platform = key.split("-")[0]
            data[platform] = {
                "token": bot.token if hasattr(bot, "token") else "",
                "enabled": True,
                "workspace": bot.workspace,
            }
        with open(self._config_path, "w") as f:
            json.dump(data, f, indent=2)

    def add_bot(self, platform: Platform, token: str, workspace: str = ".") -> Any:
        """Add a messaging bot."""
        if platform == Platform.TELEGRAM:
            bot = TelegramBot(token=token, workspace=workspace)
        elif platform == Platform.SLACK:
            bot = SlackBot(bot_token=token, workspace=workspace)
        elif platform == Platform.DISCORD:
            bot = DiscordBot(token=token, workspace=workspace)
        else:
            return None
        
        self.bots[platform.value] = bot
        self._save_config()
        return bot

    def remove_bot(self, platform: Platform):
        """Remove a messaging bot."""
        bot = self.bots.pop(platform.value, None)
        if bot and hasattr(bot, "stop"):
            bot.stop()
        self._save_config()

    def list_bots(self) -> list[dict]:
        """List configured bots."""
        return [
            {"platform": k, "enabled": True}
            for k in self.bots.keys()
        ]
