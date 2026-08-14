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
                    "current_plan_ref": args[10],
                    "pending_goal": args[11],
                    "last_route": args[12],
                    "summary": args[13],
                    "version": args[14],
                    "created_at": self.memory_table.get(chat_id, {}).get("created_at", now),
                    "updated_at": now,
                }
            return now

        if "INSERT INTO agent_conversation_memory (" in clean_q or "INSERT INTO agent_conversation_memory (" in clean_q:
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
                "current_plan_ref": args[10],
                "pending_goal": args[11],
                "last_route": args[12],
                "summary": args[13],
                "version": args[14],
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
                "extracted_by": args[15],
                "observed_at": now,
                "expires_at": None,
                "created_at": now,
                "updated_at": now,
            }
            return

        if "UPDATE agent_conversation_memory_facts SET status = 'superseded'" in clean_q:
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

    def test_2_append_facts_existing_chat(self):
        fact1 = MemoryFact(
            fact_id="f_ex_1",
            fact_type="destination",
            key="destination",
            value="Đà Nẵng",
            provenance=FactProvenance(source_turn=1, source_excerpt="Đi Đà Nẵng", extracted_by="llm", confidence=0.9),
        )
        asyncio.run(self.repo.append_facts("chat_exist", 10, [fact1], expected_version=0))

        fact2 = MemoryFact(
            fact_id="f_ex_2",
            fact_type="duration",
            key="duration",
            value=3,
            value_type="int",
            provenance=FactProvenance(source_turn=2, source_excerpt="3 ngày", extracted_by="llm", confidence=0.95),
        )
        res = asyncio.run(self.repo.append_facts("chat_exist", 10, [fact2], expected_version=1))
        self.assertEqual(res.version, 2)

    def test_11_multiple_place_candidates_same_key_allowed(self):
        fact1 = MemoryFact(
            fact_id="f_cand_1",
            fact_type="place_candidate",
            key="place_candidate",
            value="Hồ Hoàn Kiếm",
            provenance=FactProvenance(source_turn=1, source_excerpt="Đi Hồ Hoàn Kiếm", extracted_by="llm", confidence=0.9),
        )
        fact2 = MemoryFact(
            fact_id="f_cand_2",
            fact_type="place_candidate",
            key="place_candidate",
            value="Văn Miếu",
            provenance=FactProvenance(source_turn=1, source_excerpt="Ghé Văn Miếu", extracted_by="llm", confidence=0.9),
        )
        res = asyncio.run(self.repo.append_facts("chat_places_same_key", 1, [fact1, fact2], expected_version=0))
        self.assertEqual(len(res.active_facts), 2)
        active_vals = {f.value for f in res.active_facts}
        self.assertIn("Hồ Hoàn Kiếm", active_vals)
        self.assertIn("Văn Miếu", active_vals)

    def test_12_normalized_value_deduplication_supersedes_duplicate(self):
        fact1 = MemoryFact(
            fact_id="f_norm_1",
            fact_type="place_candidate",
            key="place_candidate",
            value=" Hồ Hoàn Kiếm ",
            provenance=FactProvenance(source_turn=1, source_excerpt="Hồ Hoàn Kiếm", extracted_by="llm", confidence=0.8),
        )
        asyncio.run(self.repo.append_facts("chat_dedup", 1, [fact1], expected_version=0))

        fact2 = MemoryFact(
            fact_id="f_norm_2",
            fact_type="place_candidate",
            key="place_candidate",
            value="hồ  hoàn kiếm",
            provenance=FactProvenance(source_turn=2, source_excerpt="hồ hoàn kiếm", extracted_by="llm", confidence=0.95),
        )
        res = asyncio.run(self.repo.append_facts("chat_dedup", 1, [fact2], expected_version=1))
        self.assertEqual(len(res.active_facts), 1)
        self.assertEqual(res.active_facts[0].fact_id, "f_norm_2")
        self.assertEqual(self.conn.facts_table["f_norm_1"]["status"], "superseded")

    def test_3_rollback_on_error(self):
        fact = MemoryFact(
            fact_id="f_bad",
            fact_type="destination",
            key="destination",
            value="Nha Trang",
            provenance=FactProvenance(source_turn=1, source_excerpt="Nha Trang", extracted_by="llm", confidence=0.8),
        )
        orig_execute = self.conn.execute

        async def failing_execute(query: str, *args):
            if "INSERT INTO agent_conversation_memory_facts" in query:
                raise RuntimeError("Simulated Error")
            return await orig_execute(query, *args)

        self.conn.execute = failing_execute
        with self.assertRaises(RuntimeError):
            asyncio.run(self.repo.append_facts("chat_rollback", 1, [fact], expected_version=0))
        self.assertNotIn("chat_rollback", self.conn.memory_table)

    def test_4_version_conflict_prevents_overwrite(self):
        fact = MemoryFact(
            fact_id="f_conflict",
            fact_type="destination",
            key="destination",
            value="Huế",
            provenance=FactProvenance(source_turn=1, source_excerpt="Huế", extracted_by="llm", confidence=0.8),
        )
        with self.assertRaises(MemoryVersionConflict):
            asyncio.run(self.repo.append_facts("chat_ver_conf", 1, [fact], expected_version=5))

    def test_6_user_ownership_isolation(self):
        wm = WorkingMemoryState(chat_id="chat_priv", user_id=100, destination="Cần Thơ")
        asyncio.run(self.repo.save_working_memory(wm, expected_version=0))
        self.assertIsNone(asyncio.run(self.repo.load_working_memory("chat_priv", user_id=999)))

    def test_7_jsonb_and_travelers(self):
        wm = WorkingMemoryState(
            chat_id="chat_jsonb",
            user_id=1,
            travelers=4,
            budget={"tier": "high"},
            preferences=["gần biển"],
        )
        saved = asyncio.run(self.repo.save_working_memory(wm, expected_version=0))
        loaded = asyncio.run(self.repo.load_working_memory("chat_jsonb", user_id=1))
        self.assertEqual(loaded.travelers, 4)
        self.assertEqual(loaded.budget["tier"], "high")


if __name__ == "__main__":
    unittest.main()
