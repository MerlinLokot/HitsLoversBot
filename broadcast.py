import asyncio
import logging
from datetime import datetime
from aiogram import Bot


logging.basicConfig(
    filename=f'broadcast_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

