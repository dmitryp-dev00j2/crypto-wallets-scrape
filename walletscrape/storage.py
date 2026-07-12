import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


MIGRATIONS = [
    # version 1 - baseline
    """
    CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
    INSERT OR IGNORE INTO schema_version VALUES (1);

    CREATE TABLE IF NOT EXISTS balances (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chain TEXT NOT NULL,
        wallet TEXT NOT NULL,
        token_address TEXT NOT NULL,
        symbol TEXT,
        raw_amount TEXT NOT NULL,
        amount REAL NOT NULL,
        decimals INTEGER NOT NULL,
        timestamp INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS transfers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tx_hash TEXT NOT NULL,
        chain TEXT NOT NULL,
        wallet TEXT NOT NULL,
        from_addr TEXT,
        to_addr TEXT,
        token_address TEXT,
        raw_amount TEXT NOT NULL,
        decimals INTEGER NOT NULL,
        block_number INTEGER,
        timestamp INTEGER NOT NULL,
        UNIQUE(tx_hash, chain, wallet, from_addr, to_addr, token_address, raw_amount)
    );

    CREATE INDEX IF NOT EXISTS idx_balances_lookup ON balances(wallet, chain, timestamp);
    CREATE INDEX IF NOT EXISTS idx_transfers_wallet ON transfers(wallet, timestamp);
    """,
    # version 2 - usd value column on balances
    """
    ALTER TABLE balances ADD COLUMN usd_value REAL DEFAULT NULL;
    UPDATE schema_version SET version = 2;
    """,
]


class SQLiteStorage:
    def __init__(self, db_path: str = "data/wallets.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._run_migrations()

    def get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            # 30s timeout to prevent locked database errors during rapid rpc batches
            self._conn = sqlite3.connect(self.db_path, timeout=30.0)
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA synchronous=NORMAL;")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _run_migrations(self):
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'")
        exists = cur.fetchone()

        current_ver = 0
        if exists:
            cur.execute("SELECT version FROM schema_version LIMIT 1")
            row = cur.fetchone()
            if row:
                current_ver = row[0]

        for idx, sql in enumerate(MIGRATIONS):
            target_ver = idx + 1
            if target_ver > current_ver:
                with conn:
                    conn.executescript(sql)

    def save_balances(self, balances: List[Dict[str, Any]]):
        if not balances:
            return
        conn = self.get_conn()
        sql = """
        INSERT INTO balances (chain, wallet, token_address, symbol, raw_amount, amount, decimals, timestamp, usd_value)
        VALUES (:chain, :wallet, :token_address, :symbol, :raw_amount, :amount, :decimals, :timestamp, :usd_value)
        """
        cleaned = []
        for b in balances:
            item = dict(b)
            if "usd_value" not in item:
                item["usd_value"] = None
            cleaned.append(item)

        with conn:
            conn.executemany(sql, cleaned)

    def save_transfers(self, transfers: List[Dict[str, Any]]):
        if not transfers:
            return
        conn = self.get_conn()
        sql = """
        INSERT OR IGNORE INTO transfers (tx_hash, chain, wallet, from_addr, to_addr, token_address, raw_amount, decimals, block_number, timestamp)
        VALUES (:tx_hash, :chain, :wallet, :from_addr, :to_addr, :token_address, :raw_amount, :decimals, :slot, :timestamp)
        """
        cleaned = []
        for t in transfers:
            row = dict(t)
            if "slot" not in row and "block_number" in row:
                row["slot"] = row["block_number"]
            elif "slot" not in row:
                row["slot"] = None
            cleaned.append(row)
        with conn:
            conn.executemany(sql, cleaned)

    def get_latest_balance_timestamp(self, wallet: str, chain: str) -> Optional[int]:
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT MAX(timestamp) FROM balances WHERE wallet = ? AND chain = ?",
            (wallet, chain)
        )
        row = cur.fetchone()
        return row[0] if row and row[0] is not None else None

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None


class JSONLSink:
    def __init__(self, output_dir: str = "data/jsonl"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def append(self, stream_name: str, records: Iterable[Dict[str, Any]]):
        target_file = self.output_dir / f"{stream_name}.jsonl"
        with open(target_file, "a", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
