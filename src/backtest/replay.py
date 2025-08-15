"""Tick replay engine for historical backtesting."""

import pandas as pd
from typing import Dict, List, Any, Optional, AsyncGenerator
from loguru import logger

from ..exchanges.base import Quote
from ..config import Config


class TickReplay:
    """Replays historical ticks for backtesting."""

    def __init__(self, config: Config):
        self.config = config
        self.ticks_df: Optional[pd.DataFrame] = None
        self.current_index = 0
        self.speed_multiplier = 1.0  # 1.0 = real time, 2.0 = 2x speed

    def load_parquet(self, parquet_file: str):
        """Load ticks from parquet file."""
        try:
            self.ticks_df = pd.read_parquet(parquet_file)
            self.ticks_df = self.ticks_df.sort_values('ts_ns').reset_index(drop=True)
            self.current_index = 0
            
            logger.info(f"Loaded {len(self.ticks_df)} ticks from {parquet_file}")
            logger.info(f"Time range: {pd.to_datetime(self.ticks_df['ts_ns'].min(), unit='ns')} to {pd.to_datetime(self.ticks_df['ts_ns'].max(), unit='ns')}")
            
        except Exception as e:
            logger.error(f"Failed to load parquet file: {e}")
            raise

    def set_speed(self, multiplier: float):
        """Set replay speed multiplier."""
        self.speed_multiplier = multiplier
        logger.info(f"Replay speed set to {multiplier}x")

    def get_next_tick(self) -> Optional[Dict[str, Any]]:
        """Get next tick from the dataset."""
        if not self.ticks_df or self.current_index >= len(self.ticks_df):
            return None
        
        tick = self.ticks_df.iloc[self.current_index].to_dict()
        self.current_index += 1
        return tick

    def reset(self):
        """Reset replay to beginning."""
        self.current_index = 0
        logger.info("Replay reset to beginning")

    def get_progress(self) -> Dict[str, Any]:
        """Get replay progress."""
        if not self.ticks_df:
            return {"error": "No data loaded"}
        
        return {
            'current_index': self.current_index,
            'total_ticks': len(self.ticks_df),
            'progress_pct': (self.current_index / len(self.ticks_df)) * 100,
            'speed_multiplier': self.speed_multiplier
        }

    def filter_by_time(self, start_ts: Optional[int] = None, end_ts: Optional[int] = None):
        """Filter ticks by time range."""
        if not self.ticks_df:
            return
        
        if start_ts:
            self.ticks_df = self.ticks_df[self.ticks_df['ts_ns'] >= start_ts]
        
        if end_ts:
            self.ticks_df = self.ticks_df[self.ticks_df['ts_ns'] <= end_ts]
        
        self.ticks_df = self.ticks_df.reset_index(drop=True)
        self.current_index = 0
        
        logger.info(f"Filtered to {len(self.ticks_df)} ticks")
