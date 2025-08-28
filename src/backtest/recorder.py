"""Tick recorder for saving live market data to parquet files."""

import asyncio
import time
from typing import Dict, List, Any
from pathlib import Path
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from loguru import logger

from src.exchanges.base import BaseExchange
from src.config import Config


class TickRecorder:
    """Records live market data to parquet files for backtesting."""

    def __init__(self, config: Config):
        self.config = config
        self.recording = False
        self.ticks_buffer: List[Dict[str, Any]] = []
        self.buffer_size = 1000  # Flush to disk every 1000 ticks
        self.output_file = None

    async def start_recording(self, symbols: List[str], outfile: str, 
                            exchanges: Dict[str, BaseExchange]):
        """Start recording ticks for given symbols."""
        self.output_file = Path(outfile)
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Starting tick recording for {len(symbols)} symbols to {outfile}")
        self.recording = True
        
        try:
            # Start recording tasks for each exchange
            tasks = []
            for exchange_name, exchange in exchanges.items():
                if exchange.is_connected():
                    task = asyncio.create_task(
                        self._record_exchange_ticks(exchange_name, exchange, symbols)
                    )
                    tasks.append(task)
                    logger.info(f"Started recording from {exchange_name}")
                else:
                    logger.warning(f"Exchange {exchange_name} not connected, skipping")
            
            # Wait for all recording tasks
            await asyncio.gather(*tasks, return_exceptions=True)
            
        except Exception as e:
            logger.error(f"Recording failed: {e}")
            raise
        finally:
            await self.stop_recording()

    async def stop_recording(self):
        """Stop recording and flush remaining data."""
        if not self.recording:
            return
        
        logger.info("Stopping tick recording")
        self.recording = False
        
        # Flush remaining ticks
        if self.ticks_buffer:
            await self._flush_ticks()
        
        logger.info("Tick recording stopped")

    async def _record_exchange_ticks(self, exchange_name: str, exchange: BaseExchange, 
                                   symbols: List[str]):
        """Record ticks from a specific exchange."""
        try:
            async for quote in exchange.watch_quotes(symbols):
                if not self.recording:
                    break
                
                # Create tick record
                tick = {
                    'venue': exchange_name,
                    'symbol': quote.symbol,
                    'bid': quote.bid,
                    'ask': quote.ask,
                    'bid_size': quote.bid_size,
                    'ask_size': quote.ask_size,
                    'ts_exchange': quote.ts_exchange,
                    'ts_local': quote.ts_local
                }
                
                self.ticks_buffer.append(tick)
                
                # Flush if buffer is full
                if len(self.ticks_buffer) >= self.buffer_size:
                    await self._flush_ticks()
                
        except Exception as e:
            logger.error(f"Error recording from {exchange_name}: {e}")
            if self.recording:
                # Try to restart recording after delay
                await asyncio.sleep(5)
                if self.recording:
                    logger.info(f"Restarting recording from {exchange_name}")
                    await self._record_exchange_ticks(exchange_name, exchange, symbols)

    async def _flush_ticks(self):
        """Flush ticks buffer to parquet file."""
        if not self.ticks_buffer:
            return
        
        try:
            # Convert to DataFrame
            df = pd.DataFrame(self.ticks_buffer)
            
            # Convert timestamps to nanoseconds
            df['ts_ns'] = pd.to_datetime(df['ts_local'], unit='ms').astype('int64')
            
            # Write to parquet
            if self.output_file.exists():
                # Append to existing file
                existing_df = pd.read_parquet(self.output_file)
                combined_df = pd.concat([existing_df, df], ignore_index=True)
                combined_df.to_parquet(self.output_file, index=False)
            else:
                # Create new file
                df.to_parquet(self.output_file, index=False)
            
            logger.info(f"Flushed {len(self.ticks_buffer)} ticks to {self.output_file}")
            self.ticks_buffer.clear()
            
        except Exception as e:
            logger.error(f"Failed to flush ticks: {e}")

    def get_recording_status(self) -> Dict[str, Any]:
        """Get current recording status."""
        return {
            'recording': self.recording,
            'buffer_size': len(self.ticks_buffer),
            'output_file': str(self.output_file) if self.output_file else None,
            'total_ticks_recorded': len(self.ticks_buffer)  # This is just current buffer
        }
