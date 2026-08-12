from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Sequence


class EncoderUnavailable(RuntimeError):
    pass


@dataclass
class EncoderInfo:
    model_id: str
    revision: str | None
    dimension: int
    max_length: int


class Encoder:
    info: EncoderInfo

    def encode_queries(self, values: Sequence[str]):  # pragma: no cover - interface
        raise NotImplementedError

    def encode_documents(self, values: Sequence[str]):  # pragma: no cover - interface
        raise NotImplementedError


class SentenceTransformerEncoder(Encoder):
    """Adapter used by the builder and service.

    Query/document prefixes are explicit so E5-style models do not silently
    run with the wrong instruction.  Models that do not use prefixes receive
    the raw text.
    """

    def __init__(self, model_id: str | Path, *, max_length: int = 384, query_prefix: str = "", document_prefix: str = "", task: str | None = None):
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:  # pragma: no cover - depends on GPU env
            raise EncoderUnavailable(f"sentence-transformers unavailable: {exc}") from exc
        self.model = SentenceTransformer(str(model_id), trust_remote_code=True)
        self.model.max_seq_length = max_length
        self.query_prefix = query_prefix
        self.document_prefix = document_prefix
        self.task = task
        dimension = int(self.model.get_sentence_embedding_dimension())
        revision = os.getenv("HYBRID_MODEL_REVISION")
        if not revision:
            modules = getattr(self.model, "_modules", {}).values()
            for module in modules:
                config = getattr(getattr(module, "auto_model", None), "config", None)
                revision = getattr(config, "_commit_hash", None) or getattr(config, "commit_hash", None)
                if revision:
                    break
        self.info = EncoderInfo(str(model_id), revision, dimension, max_length)

    def _encode(self, values: Sequence[str], prefix: str):
        kwargs = {"normalize_embeddings": True, "convert_to_numpy": True, "show_progress_bar": False}
        if self.task:
            kwargs["task"] = self.task
        try:
            return self.model.encode([prefix + value for value in values], **kwargs)
        except TypeError:
            # Older sentence-transformers versions or a model without a
            # task-aware remote method still support ordinary encode().
            kwargs.pop("task", None)
            return self.model.encode([prefix + value for value in values], **kwargs)

    def encode_queries(self, values: Sequence[str]):
        return self._encode(values, self.query_prefix)

    def encode_documents(self, values: Sequence[str]):
        return self._encode(values, self.document_prefix)


def build_encoder(model_id: str | Path, *, max_length: int = 384) -> SentenceTransformerEncoder:
    value = str(model_id).lower()
    if "multilingual-e5" in value:
        return SentenceTransformerEncoder(model_id, max_length=max_length, query_prefix="query: ", document_prefix="passage: ")
    if "jina-embeddings-v4" in value or "jinaai/jina-embeddings-v4" in value:
        return SentenceTransformerEncoder(model_id, max_length=max_length, task="retrieval")
    # BGE-M3, mGTE and Qwen3 expose model-card-specific instructions through
    # their remote SentenceTransformer wrapper; raw text is the safe baseline
    # until the screening run records an exact revision and prompt.
    return SentenceTransformerEncoder(model_id, max_length=max_length)
