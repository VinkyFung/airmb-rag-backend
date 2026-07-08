import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from app.core.database import AsyncSessionFactory
from app.schemas.embedding import FaqEmbeddingRebuildItem, FaqEmbeddingTaskData
from app.services.faq_embedding import FaqEmbeddingService

TERMINAL_STATUSES = {"succeeded", "partial_failed", "failed"}


@dataclass
class FaqEmbeddingTask:
    task_id: str
    limit: int
    only_pending: bool
    faq_ids: list[int] | None
    status: str = "pending"
    total: int = 0
    progress: int = 0
    succeeded: int = 0
    failed: int = 0
    message: str = "后台任务已创建，等待开始处理"
    items: list[FaqEmbeddingRebuildItem] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def to_schema(self) -> FaqEmbeddingTaskData:
        return FaqEmbeddingTaskData(
            task_id=self.task_id,
            status=self.status,
            limit=self.limit,
            only_pending=self.only_pending,
            faq_ids=self.faq_ids,
            total=self.total,
            progress=self.progress,
            succeeded=self.succeeded,
            failed=self.failed,
            message=self.message,
            items=self.items,
            created_at=self.created_at.isoformat(),
            started_at=self.started_at.isoformat() if self.started_at else None,
            finished_at=self.finished_at.isoformat() if self.finished_at else None,
        )


class FaqEmbeddingTaskManager:
    def __init__(self) -> None:
        self._tasks: dict[str, FaqEmbeddingTask] = {}

    def create_rebuild_task(
        self,
        *,
        limit: int,
        only_pending: bool,
        faq_ids: list[int] | None,
        start: bool = True,
    ) -> FaqEmbeddingTaskData:
        task_id = uuid4().hex
        task = FaqEmbeddingTask(
            task_id=task_id,
            limit=limit,
            only_pending=only_pending,
            faq_ids=faq_ids,
        )
        self._tasks[task_id] = task
        if start:
            asyncio.create_task(self._run_rebuild_task(task_id))
        return task.to_schema()

    def get_task(self, task_id: str) -> FaqEmbeddingTaskData | None:
        task = self._tasks.get(task_id)
        if task is None:
            return None
        return task.to_schema()

    async def _run_rebuild_task(self, task_id: str) -> None:
        task = self._tasks[task_id]
        task.status = "running"
        task.started_at = datetime.now()
        task.message = "正在生成 FAQ 向量"

        def on_progress(item: FaqEmbeddingRebuildItem, progress: int, total: int) -> None:
            task.total = total
            task.progress = progress
            task.items.append(item)
            task.succeeded = sum(1 for current in task.items if current.success)
            task.failed = len(task.items) - task.succeeded
            task.message = f"正在处理 {progress}/{total}"

        try:
            async with AsyncSessionFactory() as session:
                service = FaqEmbeddingService(session)
                data = await service.rebuild_embeddings(
                    limit=task.limit,
                    only_pending=task.only_pending,
                    faq_ids=task.faq_ids,
                    progress_callback=on_progress,
                )
        except Exception as exc:
            task.status = "failed"
            task.message = str(exc)[:500] or "后台任务执行失败"
            task.finished_at = datetime.now()
            return

        task.total = data.total
        task.progress = data.total
        task.succeeded = data.succeeded
        task.failed = data.failed
        task.items = data.items
        task.status = "succeeded" if data.failed == 0 else "partial_failed"
        task.message = (
            f"批量生成完成：成功 {data.succeeded} 条，失败 {data.failed} 条"
        )
        task.finished_at = datetime.now()


faq_embedding_task_manager = FaqEmbeddingTaskManager()
