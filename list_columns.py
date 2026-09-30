"""Print every column's ID, type and title so you can fill in config.yaml.

Usage: python list_columns.py <board_id>
"""

import sys

from screener.config import monday_token
from screener.monday import MondayClient

if len(sys.argv) != 2:
    raise SystemExit("Usage: python list_columns.py <board_id>")

columns = MondayClient(monday_token()).list_columns(int(sys.argv[1]))
print(f"{'ID':<28} {'TYPE':<16} TITLE")
for col in columns:
    print(f"{col['id']:<28} {col['type']:<16} {col['title']}")
