import sqlite3

# Connect to database
conn = sqlite3.connect('live_cex_arbitrage_2025_08_15.sqlite')
cursor = conn.cursor()

# Check what tables exist
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("Tables in database:")
for table in tables:
    print(f"  {table[0]}")

# Check trades table
print("\nTrades table:")
cursor.execute("SELECT COUNT(*) FROM trades")
count = cursor.fetchone()[0]
print(f"  Total trades: {count}")

if count > 0:
    cursor.execute("SELECT * FROM trades LIMIT 3")
    rows = cursor.fetchall()
    print("  Sample trades:")
    for row in rows:
        print(f"    {row}")

# Check if there are other tables with data
for table in tables:
    table_name = table[0]
    if table_name != 'trades':
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        if count > 0:
            print(f"\n{table_name} table has {count} records")

conn.close()
