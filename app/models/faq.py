from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class KbFaq(Base):
    __tablename__ = "kb_faq"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    knowledge_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    category_l1: Mapped[str | None] = mapped_column(String(100))
    category_l2: Mapped[str | None] = mapped_column(String(100))
    category_l3: Mapped[str | None] = mapped_column(String(100))
    standard_question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    user_role: Mapped[str] = mapped_column(String(20), nullable=False, default="common")
    business_type: Mapped[str | None] = mapped_column(String(50))
    risk_level: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    auth_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_answer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    human_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    review_status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    embedding_input_hash: Mapped[str | None] = mapped_column(String(64))
    embedding_status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    embedding_error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(64))
    updated_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)


class KbFaqParaphrase(Base):
    __tablename__ = "kb_faq_paraphrase"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    faq_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    paraphrase_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    status: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    remark: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[str | None] = mapped_column(String(64))
    updated_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)

