from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import mysql
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.faq import FaqRepository


@pytest.mark.asyncio
async def test_list_embedding_candidates_includes_draft_and_published_faqs() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.scalars = AsyncMock(return_value=SimpleNamespace(all=lambda: []))
    repository = FaqRepository(session)

    await repository.list_embedding_candidates(limit=100, only_pending=True)

    statement = session.scalars.await_args.args[0]
    compiled_sql = str(
        statement.compile(
            dialect=mysql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "kb_faq.status IN (0, 1)" in compiled_sql
    assert "kb_faq.embedding_status != 1" in compiled_sql

