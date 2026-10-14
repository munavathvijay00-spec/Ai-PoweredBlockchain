"""Unit checks for address retention without a live database."""
import pytest

from src.ingest.address_retention import prune_addresses


class FakeDB:
    def __init__(self, *, links=False, references=(), eligible=12):
        self.links = links
        self.references = references
        self.eligible = eligible
        self.queries = []
    async def fetch(self, query, *args):
        self.queries.append(query)
        return [{"table_name": name} for name in self.references]
    async def fetchval(self, query, *args):
        self.queries.append(query)
        if "to_regclass" in query:
            return self.links
        if "information_schema.columns" in query:
            return True
        return self.eligible
    async def execute(self, query, *args):
        self.queries.append(query)
        return "DELETE 3"


@pytest.mark.asyncio
async def test_dry_run_never_deletes():
    db = FakeDB()
    assert await prune_addresses(db) == 0
    assert not any("DELETE FROM addresses" in q for q in db.queries)


@pytest.mark.asyncio
async def test_unexpected_foreign_key_fails_closed():
    db = FakeDB(references=("unknown_link_table",))
    assert await prune_addresses(db, enabled=True) == 0
    assert not any("DELETE FROM addresses" in q for q in db.queries)


@pytest.mark.asyncio
async def test_legacy_links_must_have_fk():
    db = FakeDB(links=True)
    assert await prune_addresses(db, enabled=True) == 0


@pytest.mark.asyncio
async def test_bounded_cleanup_checks_references():
    db = FakeDB(links=True, references=("transactions", "alerts", "address_transactions"))
    assert await prune_addresses(db, enabled=True, batch_size=250) == 3
    sql = next(q for q in db.queries if "DELETE FROM addresses" in q)
    assert "LIMIT $2" in sql
    assert "FOR UPDATE OF a SKIP LOCKED" in sql
    assert "address_transactions" in sql
    assert "blacklist" in sql
    assert sql.count("NOT EXISTS") >= 8
    assert "alerts" in sql


@pytest.mark.asyncio
async def test_free_tier_five_minute_cleanup_is_valid():
    db = FakeDB(references=("transactions", "alerts"))
    assert await prune_addresses(db, enabled=True, batch_size=500, minutes=5) == 3
    sql = next(q for q in db.queries if "DELETE FROM addresses" in q)
    assert "INTERVAL '1 minute'" in sql


@pytest.mark.asyncio
async def test_rejects_invalid_batch():
    with pytest.raises(ValueError):
        await prune_addresses(FakeDB(), enabled=True, batch_size=1001)


@pytest.mark.asyncio
async def test_rejects_zero_minute_retention():
    with pytest.raises(ValueError):
        await prune_addresses(FakeDB(), enabled=True, minutes=0)
