"""Persistent alarm occurrences: acknowledgement never changes a process cause."""
import datetime
import sqlite3
from pathlib import Path


class AlarmHistory:
    def __init__(self, path):
        if str(path) != ':memory:':
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        with self.db:
            self.db.execute('''CREATE TABLE IF NOT EXISTS alarm_occurrences (
                id INTEGER PRIMARY KEY, code TEXT NOT NULL, message TEXT NOT NULL,
                action TEXT NOT NULL, raised_at TEXT NOT NULL, cleared_at TEXT,
                acknowledged_at TEXT, acknowledged_by TEXT, active INTEGER NOT NULL DEFAULT 1
            )''')
            self.db.execute('''CREATE UNIQUE INDEX IF NOT EXISTS one_active_alarm_per_code
                ON alarm_occurrences(code) WHERE active=1''')

    @staticmethod
    def now():
        return datetime.datetime.now().astimezone().isoformat(timespec='seconds')

    def synchronize(self, conditions):
        """Input is [(stable code, current message, operator action), ...]."""
        incoming = {code: (message, action) for code, message, action in conditions}
        now = self.now()
        with self.db:
            existing = {r['code']: r for r in self.db.execute(
                'SELECT * FROM alarm_occurrences WHERE active=1')}
            for code, row in existing.items():
                if code not in incoming or incoming[code][0] != row['message']:
                    self.db.execute('UPDATE alarm_occurrences SET active=0,cleared_at=? WHERE id=?',
                                    (now, row['id']))
            for code, (message, action) in incoming.items():
                previous = existing.get(code)
                if previous is None or previous['message'] != message:
                    self.db.execute('''INSERT INTO alarm_occurrences
                        (code,message,action,raised_at) VALUES (?,?,?,?)''',
                        (code, message, action, now))

    def acknowledge(self, ids, operator):
        operator = str(operator).strip()
        if not operator:
            raise ValueError('Identifique o operador antes de reconhecer alarmes.')
        ids = list(dict.fromkeys(int(value) for value in ids))
        if not ids:
            return 0
        with self.db:
            changed = 0
            for alarm_id in ids:
                changed += self.db.execute('''UPDATE alarm_occurrences
                    SET acknowledged_at=?,acknowledged_by=?
                    WHERE id=? AND acknowledged_at IS NULL''',
                    (self.now(), operator, alarm_id)).rowcount
        return changed

    def current(self):
        return [dict(row) for row in self.db.execute('''SELECT * FROM alarm_occurrences
            WHERE active=1 OR acknowledged_at IS NULL ORDER BY id DESC''')]

    def history(self, limit=500):
        return [dict(row) for row in self.db.execute(
            'SELECT * FROM alarm_occurrences ORDER BY id DESC LIMIT ?', (limit,))]

    def close(self):
        self.db.close()
