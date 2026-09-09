"""Google Drive storage for backups and archives (ADR-056).

Files go to a folder inside a Shared Drive the school owns. Service accounts
have no storage of their own, so the folder must live in a shared drive the
account has been made a member of. Everything here speaks the small ``Store``
protocol so the orchestration can be tested without Google.
"""

import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

SCOPES = ["https://www.googleapis.com/auth/drive"]
FOLDER_MIME = "application/vnd.google-apps.folder"


@dataclass(frozen=True)
class RemoteFile:
    id: str
    name: str
    created: str  # RFC 3339, as Drive reports it


class Store(Protocol):
    def upload(self, path: Path, folder_id: str, mime: str = ...) -> RemoteFile: ...
    def list_files(self, folder_id: str) -> list[RemoteFile]: ...
    def delete(self, file_id: str) -> None: ...
    def download(self, file_id: str, target: Path) -> None: ...
    def find_folder(self, name: str, parent_id: str) -> str | None: ...
    def create_folder(self, name: str, parent_id: str) -> str: ...


def ensure_folder(store: Store, name: str, parent_id: str) -> str:
    existing = store.find_folder(name, parent_id)
    return existing if existing is not None else store.create_folder(name, parent_id)


class DriveStore:
    def __init__(self, service_account_json: str) -> None:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        info = json.loads(service_account_json)
        credentials = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        self._drive = build("drive", "v3", credentials=credentials, cache_discovery=False)

    def upload(
        self, path: Path, folder_id: str, mime: str = "application/octet-stream"
    ) -> RemoteFile:
        from googleapiclient.http import MediaFileUpload

        created = (
            self._drive.files()
            .create(
                body={"name": path.name, "parents": [folder_id]},
                media_body=MediaFileUpload(str(path), mimetype=mime, resumable=True),
                fields="id,name,createdTime",
                supportsAllDrives=True,
            )
            .execute()
        )
        return RemoteFile(id=created["id"], name=created["name"], created=created["createdTime"])

    def list_files(self, folder_id: str) -> list[RemoteFile]:
        """Files directly inside a folder, newest first."""
        files: list[RemoteFile] = []
        token: str | None = None
        while True:
            page = (
                self._drive.files()
                .list(
                    q=(
                        f"'{folder_id}' in parents and mimeType != '{FOLDER_MIME}' "
                        "and trashed = false"
                    ),
                    fields="nextPageToken, files(id,name,createdTime)",
                    orderBy="createdTime desc",
                    pageSize=200,
                    pageToken=token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
            files.extend(
                RemoteFile(id=item["id"], name=item["name"], created=item["createdTime"])
                for item in page.get("files", [])
            )
            token = page.get("nextPageToken")
            if not token:
                return files

    def delete(self, file_id: str) -> None:
        self._drive.files().delete(fileId=file_id, supportsAllDrives=True).execute()

    def download(self, file_id: str, target: Path) -> None:
        from googleapiclient.http import MediaIoBaseDownload

        request = self._drive.files().get_media(fileId=file_id, supportsAllDrives=True)
        with io.FileIO(target, "wb") as handle:
            downloader = MediaIoBaseDownload(handle, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

    def find_folder(self, name: str, parent_id: str) -> str | None:
        escaped = name.replace("'", "\\'")
        found = (
            self._drive.files()
            .list(
                q=(
                    f"'{parent_id}' in parents and name = '{escaped}' "
                    f"and mimeType = '{FOLDER_MIME}' and trashed = false"
                ),
                fields="files(id)",
                pageSize=1,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        files = found.get("files", [])
        return str(files[0]["id"]) if files else None

    def create_folder(self, name: str, parent_id: str) -> str:
        created = (
            self._drive.files()
            .create(
                body={"name": name, "parents": [parent_id], "mimeType": FOLDER_MIME},
                fields="id",
                supportsAllDrives=True,
            )
            .execute()
        )
        return str(created["id"])
