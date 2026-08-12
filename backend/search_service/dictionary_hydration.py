"""Lazy V4 dictionary shard reader.

Dictionary rows are deliberately not part of the main 779k-row projection.
When a local read-only mirror is configured, only shards whose prefix can
contain the requested Pali key are hydrated and kept in a tiny LRU.
"""
from __future__ import annotations

import gzip
import json
import unicodedata
from collections import OrderedDict
from pathlib import Path

from .records import Record


def _normalise(value: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", value.lower()) if unicodedata.category(ch) != "Mn")


def _read_blob(path: Path):
    with path.open("rb") as raw:
        magic = raw.read(2)
    if magic == b"\x1f\x8b":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    return json.loads(path.read_text(encoding="utf-8"))


class DictionaryHydrator:
    def __init__(self, root: Path, *, cache_size: int = 8):
        self.root = root
        self.catalog_path = root / "catalog" / "dictionaries.json"
        self.catalog: list[dict] = []
        self.shards: list[tuple[str, str, str]] = []
        self.cache: OrderedDict[str, list[dict]] = OrderedDict()
        if self.catalog_path.exists():
            self.catalog = _read_blob(self.catalog_path)
            for dictionary in self.catalog:
                table = str(dictionary.get("table") or dictionary.get("id") or "dictionary")
                for shard in dictionary.get("shards", []):
                    self.shards.append((table, str(shard.get("prefix") or ""), str(shard["file"])))
        self.cache_size = cache_size

    @property
    def available(self) -> bool:
        return bool(self.shards)

    def _candidates(self, query: str) -> list[tuple[str, str, str]]:
        needle = _normalise(query.strip())
        if not needle:
            return []
        return [(table, prefix, relative) for table, prefix, relative in self.shards if not prefix or needle.startswith(_normalise(prefix)) or _normalise(prefix).startswith(needle[:2])]

    def _load(self, relative: str) -> list[dict]:
        if relative in self.cache:
            self.cache.move_to_end(relative)
            return self.cache[relative]
        path = self.root / relative
        if not path.exists():
            return []
        payload = _read_blob(path)
        rows = list(payload.get("rows", []))
        self.cache[relative] = rows
        self.cache.move_to_end(relative)
        while len(self.cache) > self.cache_size:
            self.cache.popitem(last=False)
        return rows

    def search(self, query: str, language: str, limit: int = 100) -> list[Record]:
        needle = _normalise(query)
        if not needle:
            return []
        results: list[Record] = []
        seen: set[str] = set()
        for table, _prefix, relative in self._candidates(query):
            for row in self._load(relative):
                key = str(row.get("dict_key") or "")
                content = str(row.get("dict_content") or "")
                haystack = _normalise(key if language == "pali" else content)
                if needle not in haystack:
                    continue
                locator = f"dictionary:{table}:{row.get('id', len(results))}"
                if locator in seen:
                    continue
                seen.add(locator)
                results.append(Record(locator=locator, corpus="v4", resource_type="dictionary", row_id=int(row.get("id", len(results))), title=key, text_pali=key, text_zh=content, text_en=content, path=["词典", table], dictionary_table=table, resource_locator=f"{table}:{row.get('id', '')}", source="azure:tipitaka/v1", version="tipitaka/v1"))
                if len(results) >= limit:
                    return results
        return results
