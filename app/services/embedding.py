import os
from pathlib import Path
from typing import Any

from starlette.concurrency import run_in_threadpool

from app.core.config import settings


class EmbeddingService:
    def __init__(self) -> None:
        self._model: Any | None = None

    def _get_model(self) -> Any:
        if self._model is None:
            self._prepare_huggingface_environment()
            self._validate_device()

            from FlagEmbedding import BGEM3FlagModel

            model_name_or_path = self._resolve_model_name_or_path(settings.embedding_model)
            self._model = BGEM3FlagModel(
                model_name_or_path,
                normalize_embeddings=True,
                use_fp16=(
                    settings.embedding_use_fp16
                    and not settings.embedding_device.startswith("cpu")
                ),
                devices=settings.embedding_device,
                batch_size=settings.embedding_batch_size,
                query_max_length=settings.embedding_max_length,
                passage_max_length=settings.embedding_max_length,
                return_dense=True,
                return_sparse=False,
                return_colbert_vecs=False,
            )
        return self._model

    @staticmethod
    def _prepare_huggingface_environment() -> None:
        if settings.hf_hub_disable_symlinks_warning:
            os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

        if settings.hf_token is None:
            return

        token = settings.hf_token.get_secret_value().strip()
        if not token:
            return

        os.environ.setdefault("HF_TOKEN", token)
        os.environ.setdefault("HUGGING_FACE_HUB_TOKEN", token)

    @staticmethod
    def _validate_device() -> None:
        if not settings.embedding_device.startswith("cuda"):
            return

        import torch

        if torch.cuda.is_available():
            return

        raise RuntimeError(
            "当前配置 EMBEDDING_DEVICE=cuda，但 PyTorch 无法识别 CUDA。"
            "请安装 CUDA 版 torch，或临时改为 EMBEDDING_DEVICE=cpu。"
        )

    @staticmethod
    def _resolve_model_name_or_path(model_name_or_path: str) -> str:
        path = Path(model_name_or_path)
        if not path.exists():
            return model_name_or_path

        if (path / "config.json").exists():
            return str(path)

        master_snapshot = path / "snapshots" / "master"
        if (master_snapshot / "config.json").exists():
            return str(master_snapshot)

        snapshots_dir = path / "snapshots"
        if snapshots_dir.exists():
            for snapshot in snapshots_dir.iterdir():
                if snapshot.is_dir() and (snapshot / "config.json").exists():
                    return str(snapshot)

        return str(path)

    def _embed_texts_sync(self, texts: list[str]) -> list[list[float]]:
        cleaned_texts = [text.strip() for text in texts]
        result = self._get_model().encode(
            cleaned_texts,
            batch_size=settings.embedding_batch_size,
            max_length=settings.embedding_max_length,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        dense_vectors = result["dense_vecs"]
        return [vector.tolist() for vector in dense_vectors]

    async def embed_text(self, text: str) -> list[float]:
        vectors = await self.embed_texts([text])
        return vectors[0]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await run_in_threadpool(self._embed_texts_sync, texts)


embedding_service = EmbeddingService()
