import sys
from unittest.mock import MagicMock

# Replace psycopg2 before bot.py is imported so the module-level
# psycopg2.connect() call doesn't require a real database.
sys.modules["psycopg2"] = MagicMock()
