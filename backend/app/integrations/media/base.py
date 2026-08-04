from dataclasses import dataclass
from typing import Protocol

from fastapi import UploadFile


@dataclass(frozen=True)
class StoredPostMedia:
    filename: str
    content_type: str
    size_bytes: int


class PostMediaStorage(Protocol):
    async def save(self, upload: UploadFile, *, content_type: str) -> StoredPostMedia: ...

    def delete(self, filename: str) -> None: ...
