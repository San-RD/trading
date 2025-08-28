#!/usr/bin/env python3
"""
Startup script for the Telegram Monitoring Bot.
This bot runs 24/7 to monitor trading performance and market intelligence.
"""

import subprocess
import sys
import signal
import os

def main():
    """Start the monitoring bot."""
    print("📱 Starting Telegram Monitoring Bot...")
    print("=" * 50)
    print("🤖 This bot will run 24/7 to monitor:")
    print("   • Trading bot status and performance")
    print("   • Daily/weekly/monthly summaries")
    print("   • Market intelligence alerts")
    print("   • Whale movements and volume spikes")
    print("=" * 50)
    print("📱 Send /start to your Telegram bot to begin interaction")
    print("🛑 Press Ctrl+C to stop the monitoring bot")
    print("=" * 50)
    
    try:
        # Start monitoring bot
        process = subprocess.run([
            sys.executable, "run_monitoring_bot.py"
        ])
    except KeyboardInterrupt:
        print("\n🛑 Stopping monitoring bot...")
        print("✅ Monitoring bot stopped successfully!")

if __name__ == "__main__":
    main()
