"""Main entry point for Vanilla chatbot."""

import asyncio
import os

from dotenv import load_dotenv

from src.bot import ChatBot
from src.logging import configure_logging

# Configure logging
# Use INFO level by default - DEBUG logs are available but not enabled
# To enable debug logging, set environment variable: LOG_LEVEL=DEBUG
configure_logging(os.getenv("LOG_LEVEL", "INFO"))


async def async_main() -> None:
    """Async main function."""
    load_dotenv()

    bot_name = os.getenv("CATGIRL_NAME", "香草")
    vanilla = ChatBot(bot_name)
    await vanilla.serve()


def main() -> None:
    """Main entry point."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
