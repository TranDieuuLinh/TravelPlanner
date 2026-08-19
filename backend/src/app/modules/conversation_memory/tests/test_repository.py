"""Unit tests for PostgresMemoryRepository adapter using in-memory fake asyncpg pool."""

import asyncio
from datetime import datetime, timezone
import unittest
from typing import Any

from app.modules.conversation_memory.adapters.postgres import PostgresMemoryRepository
from app.modules.conversation_memory.contract import (
    FactProvenance,
    MemoryFact,
    WorkingMemoryState,
)
from app.modules.conversation_memory.ports import (
    MemoryNotFound,
    MemoryVersionConflict,
)


class FakeAsyncpgRecord(dict):
    def __getitem__(self, key: str) -> Any:
        return super().__getitem__(key)


class FakeAsyncpgTransaction:
    def __init__(self, conn: "FakeAsyncpgConnection") -> None:
        self.conn = conn
        self.snapshot = None

    async def __aenter__(self) -> "FakeAsyncpgTransaction":
        self.snapshot = self.conn._take_snapshot()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is not None:
            self.conn._restore_snapshot(self.snapshot)
        return False


class FakeAsyncpgConnection:
    def __init__(self) -> None:
        self.memory_table: dict[str, dict] = {}
        self.facts_table: dict[str, dict] = {}

    def _take_snapshot(self) -> tuple[dict, dict]:
        import copy
        return copy.deepcopy(self.memory_table), copy.deepcopy(self.facts_table)

    def _restore_snapshot(self, snapshot: tuple[dict, dict]) -> None:
        self.memory_table, self.facts_table = snapshot

    def transaction(self) -> FakeAsyncpgTransaction:
        return FakeAsyncpgTransaction(self)

    async def fetchrow(self, query: str, *args) -> FakeAsyncpgRecord | None:
        clean_q = " ".join(query.split())
        if "FROM agent_conversation_memory" in clean_q:
            chat_id = args[0]
            row = self.memory_table.get(chat_id)
            if not row:
                return None
            if len(args) > 1 and row["user_id"] != args[1]:
                return None
            return FakeAsyncpgRecord(row)

        if "FROM agent_conversation_memory_facts" in clean_q:
            chat_id, key = args[0], args[1]
            matches = [
                f for f in self.facts_table.values()
                if f["chat_id"] == chat_id and f["key"] == key and f["status"] == "active"
            ]
            if len(args) > 2:
                norm_val = args[2]
                matches = [m for m in matches if m["normalized_value"] == norm_val]
            return FakeAsyncpgRecord(matches[0]) if matches else None
        return None

    async def fetch(self, query: str, *args) -> list[FakeAsyncpgRecord]:
        clean_q = " ".join(query.split())
        if "FROM agent_conversation_memory_facts" in clean_q and "key = $2" in clean_q:
            chat_id, key = args[0], args[1]
            matches = [
                f for f in self.facts_table.values()
                if f["chat_id"] == chat_id and f["key"] == key and f["status"] == "active"
            ]
            if len(args) > 2:
                norm_val = args[2]
                matches = [m for m in matches if m["normalized_value"] == norm_val]
            return [FakeAsyncpgRecord(m) for m in matches]

        if "FROM agent_conversation_memory_facts WHERE chat_id = $1 AND user_id = $2 AND status = 'active'" in clean_q:
            chat_id, user_id = args[0], args[1]
            matches = [
                f for f in self.facts_table.values()
                if f["chat_id"] == chat_id and f["user_id"] == user_id and f["status"] == "active"
            ]
            matches.sort(key=lambda x: x["created_at"])
            return [FakeAsyncpgRecord(m) for m in matches]
        return []

    async def fetchval(self, query: str, *args) -> Any:
        now = datetime.now(timezone.utc)
        clean_q = " ".join(query.split())

        if "UPDATE agent_conversation_memory SET" in clean_q:
            chat_id, user_id = args[0], args[1]
            if len(args) > 14:
                self.memory_table[chat_id] = {
                    "chat_id": chat_id,
                    "user_id": user_id,
                    "destination": args[2],
                    "duration_days": args[3],
                    "travelers": args[4],
                    "budget": args[5],
                    "preferences": args[6],
                    "avoids": args[7],
                    "mentioned_places": args[8],
                    "selected_places": args[9],
                    "active_references": args[10],
                    "current_plan_ref": args[11],
                    "pending_goal": args[12],
                    "last_route": args[13],
                    "summary": args[14],
                    "version": args[15],
                    "created_at": self.memory_table.get(chat_id, {}).get("created_at", now),
                    "updated_at": now,
                }
            return now

        if "INSERT INTO agent_conversation_memory (" in clean_q:
            chat_id, user_id = args[0], args[1]
            self.memory_table[chat_id] = {
                "chat_id": chat_id,
                "user_id": user_id,
                "destination": args[2],
                "duration_days": args[3],
                "travelers": args[4],
                "budget": args[5],
                "preferences": args[6],
                "avoids": args[7],
                "mentioned_places": args[8],
                "selected_places": args[9],
                    "active_references": args[10],
                    "current_plan_ref": args[11],
                    "pending_goal": args[12],
                    "last_route": args[13],
                    "summary": args[14],
                    "version": args[15],
                "created_at": now,
                "updated_at": now,
            }
            return now
        return now

    async def execute(self, query: str, *args) -> None:
        now = datetime.now(timezone.utc)
        clean_q = " ".join(query.split())

        if "INSERT INTO agent_conversation_memory (" in clean_q and len(args) == 2:
            chat_id, user_id = args[0], args[1]
            self.memory_table[chat_id] = {
                "chat_id": chat_id,
                "user_id": user_id,
                "destination": None,
                "duration_days": None,
                "travelers": None,
                "budget": 'null',
                "preferences": '[]',
                "avoids": '[]',
                "mentioned_places": '[]',
                    "selected_places": '[]',
                    "active_references": '[]',
                "current_plan_ref": None,
                "pending_goal": None,
                "last_route": None,
                "summary": None,
                "version": 0,
                "created_at": now,
                "updated_at": now,
            }
            return

        if "INSERT INTO agent_conversation_memory_facts" in clean_q:
            fact_id, chat_id, user_id = args[0], args[1], args[2]
            if chat_id not in self.memory_table:
                raise RuntimeError(f"ForeignKeyViolation: chat_id '{chat_id}' not found")
            self.facts_table[fact_id] = {
                "fact_id": fact_id,
                "chat_id": chat_id,
                "user_id": user_id,
                "fact_type": args[3],
                "key": args[4],
                "value": args[5],
                "normalized_value": args[6],
                "value_type": args[7],
                "scope": args[8],
                "status": args[9],
                "confirmed_by_user": args[10],
                "confidence": args[11],
                "source_turn": args[12],
                "source_excerpt": args[13],
                "source_message_id": args[14],
                "source_url": args[15] if len(args) > 15 else None,
                "extracted_by": args[16] if len(args) > 16 else (args[15] if len(args) > 15 else "test"),
                "observed_at": now,
                "expires_at": None,
                "created_at": now,
                "updated_at": now,
            }
            return

        if "UPDATE agent_conversation_memory_facts SET status = 'superseded'" in clean_q:
            if "WHERE chat_id = $1 AND key = $2" in clean_q:
                chat_id, key = args[0], args[1]
                norm_val = args[2] if len(args) > 2 else None
                for fid, f in self.facts_table.items():
                    if f["chat_id"] == chat_id and f["key"] == key and f["status"] == "active":
                        if norm_val is not None:
                            if f["normalized_value"] == norm_val:
                                f["status"] = "superseded"
                                f["updated_at"] = now
                        else:
                            f["status"] = "superseded"
                            f["updated_at"] = now
            elif len(args) == 1:
                fact_id = args[0]
                if fact_id in self.facts_table:
                    self.facts_table[fact_id]["status"] = "superseded"
                    self.facts_table[fact_id]["updated_at"] = now
            return

        if "UPDATE agent_conversation_memory SET version =" in clean_q:
            chat_id, user_id, next_ver = args[0], args[1], args[2]
            if chat_id in self.memory_table:
                self.memory_table[chat_id]["version"] = next_ver
                self.memory_table[chat_id]["updated_at"] = now
            return


class FakeAsyncpgPool:
    def __init__(self, conn: FakeAsyncpgConnection) -> None:
        self.conn = conn
        self.is_acquired = False

    def acquire(self) -> "FakePoolAcquireContext":
        return FakePoolAcquireContext(self)


class FakePoolAcquireContext:
    def __init__(self, pool: FakeAsyncpgPool) -> None:
        self.pool = pool

    async def __aenter__(self) -> FakeAsyncpgConnection:
        if self.pool.is_acquired:
            raise RuntimeError("Nested pool acquire detected!")
        self.pool.is_acquired = True
        return self.pool.conn

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self.pool.is_acquired = False


class TestPostgresMemoryRepositoryAdapter(unittest.TestCase):
    def setUp(self):
        self.conn = FakeAsyncpgConnection()
        self.pool = FakeAsyncpgPool(self.conn)
        self.repo = PostgresMemoryRepository(pool=self.pool)

    def test_1_append_facts_new_chat_creates_parent(self):
        fact = MemoryFact(
            fact_id="f_new_1",
            fact_type="destination",
            key="destination",
            value="Hà Nội",
            provenance=FactProvenance(source_turn=1, source_excerpt="Đi Hà Nội", extracted_by="llm", confidence=0.9),
        )
        res = asyncio.run(self.repo.append_facts("chat_new", 10, [fact], expected_version=0))
        self.assertEqual(res.version, 1)
        self.assertIn("chat_new", self.conn.memory_table)

    def test_save_memory_and_facts_atomic_rollback(self):
        wm = WorkingMemoryState(chat_id="chat_atom", user_id=1, destination="Hà Nội")
        fact = MemoryFact(
            fact_id="f_atom_1",
            fact_type="destination",
            key="destination",
            value="Hà Nội",
            provenance=FactProvenance(source_turn=1, source_excerpt="txt", extracted_by="rule", confidence=0.9),
        )
        orig_exec = self.conn.execute

        async def failing_exec(query: str, *args):
            if "INSERT INTO agent_conversation_memory_facts" in query:
                raise RuntimeError("Simulated Fact Insert Failure")
            return await orig_exec(query, *args)

        self.conn.execute = failing_exec

        with self.assertRaises(RuntimeError):
            asyncio.run(self.repo.save_memory_and_facts(wm, [fact], expected_version=0))

        # Atomic rollback verification: projection save MUST be rolled back completely
        self.assertNotIn("chat_atom", self.conn.memory_table)

    def test_source_url_survives_save_and_load(self):
        wm = WorkingMemoryState(chat_id="chat_url", user_id=1)
        fact = MemoryFact(
            fact_id="f_url_db",
            fact_type="note",
            key="note",
            value="https://example.com/hanoi",
            provenance=FactProvenance(
                source_turn=1,
                source_excerpt="txt",
                extracted_by="rule",
                confidence=0.9,
                source_url="https://example.com/hanoi",
            ),
        )
        asyncio.run(self.repo.save_memory_and_facts(wm, [fact], expected_version=0))
        loaded = asyncio.run(self.repo.load_working_memory("chat_url", user_id=1))
        self.assertIsNotNone(loaded)
        self.assertEqual(len(loaded.active_facts), 1)
        self.assertEqual(loaded.active_facts[0].provenance.source_url, "https://example.com/hanoi")


if __name__ == "__main__":
    unittest.main()
