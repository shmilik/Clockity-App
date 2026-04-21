import sqlite3
from datetime import datetime
conn = sqlite3.connect('C:/Users/info/.autogenstudio/autogen04202.db')
cur = conn.cursor()
now = datetime.utcnow().isoformat()
cur.execute("UPDATE run SET status='ERROR', updated_at=? WHERE status='ACTIVE'", (now,))
print(f"Stopped {cur.rowcount} active run(s)")
conn.commit()
conn.close()
