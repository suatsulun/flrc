from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dump", type=Path)
    parser.add_argument("--retain", type=int, default=12)
    args = parser.parse_args()
    info = json.loads(os.environ["GDRIVE_SERVICE_ACCOUNT_JSON"])
    folder_id = os.environ["GDRIVE_BACKUP_FOLDER_ID"]
    credentials = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    drive = build("drive", "v3", credentials=credentials, cache_discovery=False)
    digest = hashlib.sha256(args.dump.read_bytes()).hexdigest()
    sidecar = args.dump.with_suffix(args.dump.suffix + ".sha256")
    sidecar.write_text(f"{digest}  {args.dump.name}\n", encoding="utf-8")
    for path, mime in ((args.dump, "application/octet-stream"), (sidecar, "text/plain")):
        drive.files().create(
            body={"name": path.name, "parents": [folder_id]},
            media_body=MediaFileUpload(str(path), mimetype=mime, resumable=True),
            fields="id,name,createdTime",
            supportsAllDrives=True,
        ).execute()
    result = (
        drive.files()
        .list(
            q=f"'{folder_id}' in parents and name contains 'flrc-' and trashed = false",
            fields="files(id,name,createdTime)",
            orderBy="createdTime desc",
            pageSize=100,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )
    dumps = [item for item in result.get("files", []) if item["name"].endswith(".dump")]
    for old in dumps[args.retain :]:
        drive.files().delete(fileId=old["id"], supportsAllDrives=True).execute()
    print(
        json.dumps(
            {"uploaded": args.dump.name, "sha256": digest, "retained": min(len(dumps), args.retain)}
        )
    )


if __name__ == "__main__":
    main()
