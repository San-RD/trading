"""Basic tests for the cross-exchange arbitrage bot."""

import pytest
import asyncio
from unittest.mock import Mock, patch

from src.config import Config
from src.core.detector import ArbitrageDetector
from src.core.executor import ArbitrageExecutor
from src.exchanges.base import BaseExchange


class TestBasicImports:
    """Test that basic modules can be imported."""
    
    def test_config_import(self):
        """Test config module import."""
        assert Config is not None
    
    def test_detector_import(self):
        """Test detector module import."""
        assert ArbitrageDetector is not None
    
    def test_executor_import(self):
        """Test executor module import."""
        assert ArbitrageExecutor is not None
    
    def test_exchange_base_import(self):
        """Test exchange base module import."""
        assert BaseExchange is not None


class TestConfig:
    """Test configuration functionality."""
    
    def test_config_structure(self):
        """Test config has expected structure."""
        # This is a basic test - in practice you'd load from a test config file
        config = Config(
            exchanges=Mock(),
            fees=Mock(),
            symbols=Mock(),
            detector=Mock(),
            execution=Mock(),
            inventory=Mock(),
            backtest=Mock(),
            alerts=Mock(),
            storage=Mock(),
            logging=Mock(),
            server=Mock()
        )
        
        assert hasattr(config, 'exchanges')
        assert hasattr(config, 'detector')
        assert hasattr(config, 'execution')


class TestDetector:
    """Test arbitrage detector."""
    
    def test_detector_creation(self):
        """Test detector can be created."""
        mock_config = Mock()
        mock_config.detector.min_edge_bps = 8.0
        mock_config.detector.min_book_bbo_age_ms = 600
        mock_config.detector.max_spread_bps = 20.0
        mock_config.detector.max_notional_usdt = 10000.0
        mock_config.detector.slippage_model = "linear"
        
        detector = ArbitrageDetector(mock_config)
        assert detector is not None
        assert detector.min_edge_bps == 8.0


class TestExecutor:
    """Test trade executor."""
    
    def test_executor_creation(self):
        """Test executor can be created."""
        mock_config = Mock()
        mock_config.execution.type = "IOC"
        mock_config.execution.guard_bps = 3.0
        mock_config.execution.max_leg_latency_ms = 200
        mock_config.execution.hedge.atomic = True
        mock_config.execution.hedge.cancel_on_partial = True
        
        mock_exchanges = {}
        mode = "paper"
        
        executor = ArbitrageExecutor(mock_config, mock_exchanges, mode)
        assert executor is not None
        assert executor.mode == "paper"
        assert executor.execution_type == "IOC"


if __name__ == "__main__":
    pytest.main([__file__])
