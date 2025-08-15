import sqlite3
import json
from datetime import datetime

def show_paper_trade():
    try:
        conn = sqlite3.connect('arb.sqlite')
        cursor = conn.cursor()
        
        print("=== PAPER TRADE DATA ===\n")
        
        # Show opportunities
        cursor.execute("SELECT * FROM opportunities")
        opportunities = cursor.fetchall()
        
        if opportunities:
            print("📊 ARBITRAGE OPPORTUNITY DETECTED:")
            opp = opportunities[0]
            print(f"  Symbol: {opp[2]}")
            print(f"  Direction: {opp[3]}")
            print(f"  Edge: {opp[4]:.2f} bps")
            print(f"  Notional: ${opp[5]:,.2f}")
            print(f"  Expected Profit: ${opp[6]:.2f}")
            print(f"  Timestamp: {datetime.fromtimestamp(opp[1]/1000)}")
            
            # Parse metadata
            try:
                metadata = json.loads(opp[7])
                print(f"  Buy Exchange: {metadata.get('buy_exchange', 'N/A')}")
                print(f"  Sell Exchange: {metadata.get('sell_exchange', 'N/A')}")
                print(f"  Buy Fee: {metadata.get('buy_fee_bps', 'N/A')} bps")
                print(f"  Sell Fee: {metadata.get('sell_fee_bps', 'N/A')} bps")
            except:
                print(f"  Metadata: {opp[7]}")
        
        # Show trades
        cursor.execute("SELECT * FROM trades")
        trades = cursor.fetchall()
        
        if trades:
            print(f"\n💼 EXECUTED TRADES ({len(trades)}):")
            for trade in trades:
                print(f"  Trade ID: {trade[0]}")
                print(f"  Symbol: {trade[1]}")
                print(f"  Side: {trade[2]}")
                print(f"  Quantity: {trade[3]}")
                print(f"  Price: ${trade[4]:.4f}")
                print(f"  Exchange: {trade[5]}")
                print(f"  Timestamp: {datetime.fromtimestamp(trade[6]/1000)}")
                print(f"  Order ID: {trade[7]}")
                print("  ---")
        
        # Show orders
        cursor.execute("SELECT * FROM orders")
        orders = cursor.fetchall()
        
        if orders:
            print(f"\n📋 ORDER DETAILS ({len(orders)}):")
            for order in orders:
                print(f"  Order ID: {order[0]}")
                print(f"  Symbol: {order[1]}")
                print(f"  Side: {order[2]}")
                print(f"  Type: {order[3]}")
                print(f"  Quantity: {order[4]}")
                print(f"  Price: ${order[5]:.4f}")
                print(f"  Status: {order[6]}")
                print(f"  Exchange: {order[7]}")
                print("  ---")
        
        # Show fills
        cursor.execute("SELECT * FROM fills")
        fills = cursor.fetchall()
        
        if fills:
            print(f"\n✅ FILL DETAILS ({len(fills)}):")
            for fill in fills:
                print(f"  Fill ID: {fill[0]}")
                print(f"  Order ID: {fill[1]}")
                print(f"  Quantity: {fill[2]}")
                print(f"  Price: ${fill[3]:.4f}")
                print(f"  Fee: ${fill[4]:.4f}")
                print(f"  Timestamp: {datetime.fromtimestamp(fill[5]/1000)}")
                print("  ---")
        
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    show_paper_trade()
