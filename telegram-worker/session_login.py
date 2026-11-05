import asyncio
import getpass
from telethon import TelegramClient
from telethon.sessions import StringSession

async def main():
    api_id = int(input("Telegram API ID: ").strip())
    api_hash = getpass.getpass("Telegram API Hash (hidden): ").strip()
    phone = input("Phone number with country code: ").strip()
    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.start(
        phone=phone,
        code_callback=lambda: input("Telegram login code: ").strip(),
        password=lambda: getpass.getpass("Telegram 2-step password (hidden): "),
    )
    print("\nPRIVATE TELEGRAM SESSION STRING — copy it to GitHub Actions secret TELEGRAM_SESSION_STRING:")
    print(client.session.save())
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
