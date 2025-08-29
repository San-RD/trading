#!/usr/bin/env python3
"""
Test script to verify configuration loading with environment variables.
Run this to check if your config.yaml and environment variables are working correctly.
"""

import os
import sys
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ Loaded environment variables from .env file")
except ImportError:
    print("⚠️  python-dotenv not installed. Install with: pip install python-dotenv")
    print("   Or manually set environment variables in your shell")
except Exception as e:
    print(f"⚠️  Error loading .env file: {e}")

# Add src to path
sys.path.append(str(Path(__file__).parent / "src"))

def test_config_loading():
    """Test if configuration can be loaded successfully."""
    try:
        from src.config import Config
        
        print("🔍 Testing configuration loading...")
        
        # Check if required environment variables are set
        required_vars = [
            "BINANCE_API_KEY",
            "BINANCE_SECRET_KEY", 
            "KRAKEN_API_KEY",
            "KRAKEN_SECRET_KEY",
            "HYPERLIQUID_WALLET_ADDRESS",
            "HYPERLIQUID_PRIVATE_KEY",
            "TELEGRAM_BOT_TOKEN",
            "TELEGRAM_CHAT_ID"
        ]
        
        missing_vars = []
        for var in required_vars:
            value = os.getenv(var)
            if not value:
                missing_vars.append(var)
            else:
                print(f"🔍 {var}: {value[:20]}... (type: {type(value).__name__})")
        
        if missing_vars:
            print(f"❌ Missing environment variables: {', '.join(missing_vars)}")
            print("Please set these in your .env file")
            return False
        
        print("✅ All required environment variables are set")
        
        # Try to load configuration
        try:
            config = Config.load_from_file("config.yaml")
            print("✅ Configuration loaded successfully!")
            
            # Test some key values
            print(f"📊 Trading mode: {getattr(config, 'trading_mode', 'N/A')}")
            print(f"🔑 Binance key: {config.exchanges.accounts['binance'].key[:10]}...")
            print(f"🔑 Kraken key: {config.exchanges.accounts['kraken'].key[:10]}...")
            print(f"🔑 Hyperliquid wallet: {config.hyperliquid.wallet_address[:10]}...")
            print(f"📱 Telegram token: {config.alerts.telegram_token[:10]}...")
            print(f"💾 Database path: {config.storage.db_path}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error loading configuration: {e}")
            return False
            
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_environment_substitution():
    """Test if environment variable substitution works in config.yaml."""
    try:
        with open("config.yaml", "r") as f:
            content = f.read()
        
        # Check if environment variables are referenced
        if "${BINANCE_API_KEY}" in content:
            print("✅ Environment variable substitution configured in config.yaml")
            return True
        else:
            print("❌ Environment variable substitution not found in config.yaml")
            return False
            
    except Exception as e:
        print(f"❌ Error reading config.yaml: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Tri-Arb Bot Configuration Test")
    print("=" * 40)
    
    # Test environment substitution
    env_test = test_environment_substitution()
    
    # Test configuration loading
    config_test = test_config_loading()
    
    print("\n" + "=" * 40)
    if env_test and config_test:
        print("🎉 All tests passed! Configuration is ready to use.")
        print("\nNext steps:")
        print("1. Copy env.example to .env")
        print("2. Fill in your actual API keys in .env")
        print("3. Run your bot!")
    else:
        print("❌ Some tests failed. Please check the errors above.")
        print("\nTroubleshooting:")
        print("1. Make sure you have a .env file with all required variables")
        print("2. Check that config.yaml uses environment variable syntax (${VAR_NAME})")
        print("3. Verify that all required environment variables are set")
