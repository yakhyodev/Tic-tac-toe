import asyncio

from config import Settings
from database import db


async def main() -> None:
    settings = Settings.from_env()
    await db.connect(settings.database_url)
    try:
        await db.migrate()
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
