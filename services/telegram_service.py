from typing import Union
from telethon import TelegramClient, events
import asyncio
import os


class TelegramLogFetcher:
    def __init__(self, api_id: int, api_hash: str, session_name: str = "tg"):
        self.client = TelegramClient(session_name, api_id, api_hash)
        self.group_id = 1943303299
        self.bot_username = "ysxfetx_bot"
        self.current_query_msg = None
        self.response_received = asyncio.Event()
        self.download_path = None
        self.result_count = None
        self._event_handler = None

    async def _handle_bot_response(self, event):
        """Handle incoming messages from the bot"""
        if self.current_query_msg:
            if event.sender.username == self.bot_username:
                if (
                    event.is_reply
                    and event.reply_to.reply_to_msg_id == self.current_query_msg.id
                ):
                    message_text = event.raw_text
                    self.result_count = None

                    for line in message_text.split("\n"):
                        if "🔎" in line and "result(s)" in line:
                            parts = line.replace("🔎", "").strip().split()
                            for part in parts:
                                if part.isdigit():
                                    self.result_count = int(part)
                                    break
                            break

                    if event.file:
                        os.makedirs("downloads", exist_ok=True)
                        self.download_path = await event.download_media(
                            f"downloads/{event.id}"
                        )
                        self.response_received.set()
                    elif self.result_count == 0:
                        self.download_path = None
                        self.response_received.set()

    async def fetch_logs(self, query: str, timeout: int = 30) -> Union[str, int]:
        """Send query and wait for response (file or 0 results)"""
        self.result_count = None
        self.download_path = None
        self.current_query_msg = None
        self.response_received.clear()

        try:
            await self.client.start()
            self._event_handler = self.client.add_event_handler(
                self._handle_bot_response, events.NewMessage(chats=self.group_id)
            )

            self.client.add_event_handler(
                self._handle_bot_response, events.NewMessage(chats=self.group_id)
            )

            self.current_query_msg = await self.client.send_message(
                self.group_id, f"/s {query}"
            )

            try:
                await asyncio.wait_for(self.response_received.wait(), timeout=timeout)
                return self.download_path, self.result_count
            except asyncio.TimeoutError:
                return None, None
        except Exception as e:
            return None, None
        finally:
            # Cleanup
            if self._event_handler:
                self.client.remove_event_handler(self._event_handler)
                self._event_handler = None

            if self.current_query_msg:
                try:
                    await self.current_query_msg.delete()
                except Exception as e:
                    print(e)

            await self.client.disconnect()
