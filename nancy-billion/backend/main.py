#!/usr/bin/env python3
"""
Nancy/Billion AI Assistant - Main Backend Entry Point
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent))

from core.assistant import NancyBillionAssistant
from config.settings import Settings
from utils.logger import setup_logging

async def main():
    """Main entry point for the Nancy/Billion AI Assistant"""
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("Starting Nancy/Billion AI Assistant...")
    
    try:
        # Load settings
        settings = Settings()
        
        # Initialize the assistant
        assistant = NancyBillionAssistant(settings)
        
        # Setup signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            asyncio.create_task(assistant.shutdown())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Start the assistant
        await assistant.start()
        
        # Keep running until shutdown signal
        await assistant.wait_for_shutdown()
        
    except Exception as e:
        logger.error(f"Fatal error in main: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("Nancy/Billion AI Assistant shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())