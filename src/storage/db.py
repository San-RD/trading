"""Database operations for cross-exchange arbitrage bot."""

import sqlite3
import asyncio
from typing import Dict, List, Any, Optional
from pathlib import Path
from loguru import logger
import time
from datetime import datetime, timedelta

from .models import Opportunity, Order, Fill, Trade, BalanceSnapshot


class Database:
    """SQLite database interface."""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.connection: Optional[sqlite3.Connection] = None

    async def connect(self):
        """Connect to database."""
        try:
            self.connection = sqlite3.connect(self.db_path)
            await self._create_tables()
            logger.info(f"Connected to database: {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    async def disconnect(self):
        """Disconnect from database."""
        if self.connection:
            self.connection.close()
            self.connection = None
            logger.info("Disconnected from database")

    async def _create_tables(self):
        """Create database tables if they don't exist."""
        if not self.connection:
            return
        
        try:
            cursor = self.connection.cursor()
            
            # Create opportunities table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS opportunities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    edge_bps REAL NOT NULL,
                    notional REAL NOT NULL,
                    expected_profit REAL NOT NULL,
                    metadata TEXT
                )
            """)
            
            # Create orders table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT NOT NULL,
                    venue TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    price REAL NOT NULL,
                    qty REAL NOT NULL,
                    status TEXT NOT NULL,
                    ts_sent INTEGER NOT NULL,
                    ts_filled INTEGER,
                    metadata TEXT
                )
            """)
            
            # Create fills table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS fills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    price REAL NOT NULL,
                    qty REAL NOT NULL,
                    fee_asset TEXT NOT NULL,
                    fee REAL NOT NULL,
                    ts INTEGER NOT NULL,
                    FOREIGN KEY (order_id) REFERENCES orders (id)
                )
            """)
            
            # Create trades table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    pnl_usdt REAL NOT NULL,
                    edge_bps REAL NOT NULL,
                    latency_ms_total INTEGER NOT NULL,
                    mode TEXT NOT NULL,
                    notes TEXT,
                    ts INTEGER NOT NULL
                )
            """)
            
            # Create balances table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS balances (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    venue TEXT NOT NULL,
                    asset TEXT NOT NULL,
                    free REAL NOT NULL,
                    total REAL NOT NULL,
                    ts INTEGER NOT NULL
                )
            """)
            
            self.connection.commit()
            logger.info("Database tables created/verified")
            
        except Exception as e:
            logger.error(f"Failed to create tables: {e}")
            raise

    async def insert_opportunity(self, opportunity) -> int:
        """Insert opportunity record."""
        if not self.connection:
            return 0
        
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT INTO opportunities (timestamp, symbol, direction, edge_bps, notional, expected_profit, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                opportunity.detected_at,
                opportunity.symbol,
                opportunity.direction.value,
                opportunity.net_edge_bps,
                opportunity.notional_value,
                opportunity.expected_profit_usdt,
                str(opportunity.metadata)
            ))
            
            self.connection.commit()
            return cursor.lastrowid
            
        except Exception as e:
            logger.error(f"Failed to insert opportunity: {e}")
            return 0

    async def insert_execution(self, execution_result) -> int:
        """Insert execution result."""
        if not self.connection:
            return 0
        
        try:
            cursor = self.connection.cursor()
            
            # Insert trade record
            cursor.execute("""
                INSERT INTO trades (symbol, direction, pnl_usdt, edge_bps, latency_ms_total, mode, notes, ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                execution_result.opportunity.symbol,
                execution_result.opportunity.direction.value,
                execution_result.realized_pnl,
                execution_result.opportunity.net_edge_bps,
                execution_result.execution_time_ms,
                'paper' if not execution_result.metadata or 'mode' not in execution_result.metadata else execution_result.metadata['mode'],
                execution_result.error or '',
                int(time.time() * 1000)
            ))
            
            self.connection.commit()
            return cursor.lastrowid
            
        except Exception as e:
            logger.error(f"Failed to insert execution: {e}")
            return 0

    async def get_performance_summary(self, days: int) -> Dict[str, Any]:
        """Get performance summary for last N days."""
        if not self.connection:
            return {}
        
        try:
            cursor = self.connection.cursor()
            
            # Get trades from last N days
            cutoff_time = int(time.time() * 1000) - (days * 24 * 60 * 60 * 1000)
            
            cursor.execute("""
                SELECT COUNT(*), SUM(pnl_usdt), AVG(edge_bps), AVG(latency_ms_total)
                FROM trades 
                WHERE ts > ?
            """, (cutoff_time,))
            
            result = cursor.fetchone()
            if result and result[0] > 0:
                total_trades, total_pnl, avg_edge, avg_latency = result
                win_rate = len([r for r in cursor.fetchall() if r[1] > 0]) / total_trades
                
                return {
                    'summary': {
                        'total_trades': total_trades,
                        'win_rate': win_rate,
                        'total_pnl': total_pnl or 0.0,
                        'avg_edge_bps': avg_edge or 0.0,
                        'avg_latency_ms': avg_latency or 0.0
                    }
                }
            else:
                return {
                    'summary': {
                        'total_trades': 0,
                        'win_rate': 0.0,
                        'total_pnl': 0.0,
                        'avg_edge_bps': 0.0,
                        'avg_latency_ms': 0.0
                    }
                }
                
        except Exception as e:
            logger.error(f"Failed to get performance summary: {e}")
            return {}

    async def get_recent_opportunities(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent arbitrage opportunities."""
        if not self.connection:
            return []
        
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                SELECT timestamp, symbol, direction, edge_bps, notional, expected_profit
                FROM opportunities 
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (limit,))
            
            opportunities = []
            for row in cursor.fetchall():
                opportunities.append({
                    'timestamp': row[0],
                    'symbol': row[1],
                    'direction': row[2],
                    'edge_bps': row[3],
                    'notional': row[4],
                    'expected_profit': row[5]
                })
            
            return opportunities
            
        except Exception as e:
            logger.error(f"Failed to get recent opportunities: {e}")
            return []


class DatabaseManager:
    """Simple database manager interface for monitoring bot."""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            # Try to find the database from config or use default
            try:
                from src.config import Config
                config = Config.load_from_file("config.yaml")
                db_path = config.storage.db_path
            except:
                db_path = "arb.sqlite"  # fallback
        
        self.db = Database(db_path)
        self.logger = logger
    
    async def connect(self):
        """Connect to database."""
        await self.db.connect()
    
    async def disconnect(self):
        """Disconnect from database."""
        await self.db.disconnect()
    
    async def get_recent_trades(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent trades from database."""
        try:
            await self.db.connect()
            cursor = self.db.connection.cursor()
            
            cursor.execute("""
                SELECT id, symbol, direction, pnl_usdt, edge_bps, 
                       ts, latency_ms_total, mode, notes
                FROM trades 
                ORDER BY ts DESC 
                LIMIT ?
            """, (limit,))
            
            trades = []
            for row in cursor.fetchall():
                # Convert timestamp from milliseconds to datetime
                timestamp = datetime.fromtimestamp(row[5] / 1000) if row[5] else None
                
                trades.append({
                    'id': row[0],
                    'symbol': row[1],
                    'direction': row[2],
                    'pnl': row[3] or 0.0,
                    'edge_bps': row[4],
                    'timestamp': timestamp,
                    'latency_ms': row[6],
                    'mode': row[7],
                    'notes': row[8]
                })
            
            return trades
            
        except Exception as e:
            self.logger.error(f"Failed to get recent trades: {e}")
            return []
        finally:
            await self.db.disconnect()
    
    async def get_trades_in_period(self, start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
        """Get trades in a time period from database."""
        try:
            await self.db.connect()
            cursor = self.db.connection.cursor()
            
            # Convert datetime to milliseconds timestamp
            start_ts = int(start_time.timestamp() * 1000)
            end_ts = int(end_time.timestamp() * 1000)
            
            cursor.execute("""
                SELECT id, symbol, direction, pnl_usdt, edge_bps, 
                       ts, latency_ms_total, mode, notes
                FROM trades 
                WHERE ts >= ? AND ts <= ?
                ORDER BY ts DESC
            """, (start_ts, end_ts))
            
            trades = []
            for row in cursor.fetchall():
                # Convert timestamp from milliseconds to datetime
                timestamp = datetime.fromtimestamp(row[5] / 1000) if row[5] else None
                
                trades.append({
                    'id': row[0],
                    'symbol': row[1],
                    'direction': row[2],
                    'pnl': row[3] or 0.0,
                    'edge_bps': row[4],
                    'timestamp': timestamp,
                    'latency_ms': row[6],
                    'mode': row[7],
                    'notes': row[8]
                })
            
            return trades
            
        except Exception as e:
            self.logger.error(f"Failed to get trades in period: {e}")
            return []
        finally:
            await self.db.disconnect()
    
    async def get_latest_session(self):
        """Get latest session info from database."""
        try:
            await self.db.connect()
            cursor = self.db.connection.cursor()
            
            cursor.execute("""
                SELECT MIN(ts) as session_start, MAX(ts) as session_end,
                       COUNT(*) as total_trades, SUM(pnl_usdt) as total_pnl
                FROM trades
                WHERE ts >= ? 
            """, (int((datetime.now() - timedelta(days=1)).timestamp() * 1000),))
            
            row = cursor.fetchone()
            if row and row[0]:
                session_start = datetime.fromtimestamp(row[0] / 1000)
                session_end = datetime.fromtimestamp(row[1] / 1000) if row[1] else None
                
                return {
                    'session_start': session_start,
                    'session_end': session_end,
                    'total_trades': row[2] or 0,
                    'total_pnl': row[3] or 0.0
                }
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to get latest session: {e}")
            return None
        finally:
            await self.db.disconnect()
