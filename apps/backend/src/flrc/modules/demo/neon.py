"""The two Neon API calls the demo reset needs.

A restore replaces the demo branch's data and schema with the head of its
pristine parent while keeping the branch id, compute, and connection string;
existing connections are interrupted for a moment. Only a project-scoped key
is used, and it never appears in logs or telemetry.
"""

import asyncio

import httpx2

API_BASE = "https://console.neon.tech/api/v2"
FINISHED_STATES = {"finished"}
FAILED_STATES = {"failed", "error", "cancelled", "skipped"}


class NeonError(RuntimeError):
    """The Neon API refused or failed a reset step; the message is machine text only."""


class NeonClient:
    def __init__(self, *, api_key: str, project_id: str, timeout: float = 20.0) -> None:
        self._api_key = api_key
        self._project_id = project_id
        self._timeout = timeout

    def _client(self) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(
            base_url=API_BASE,
            timeout=self._timeout,
            headers={"authorization": f"Bearer {self._api_key}", "accept": "application/json"},
        )

    async def reset_branch_from(self, branch_id: str, source_branch_id: str) -> list[str]:
        """Restore `branch_id` to the head of `source_branch_id`; return operation ids."""
        try:
            async with self._client() as client:
                response = await client.post(
                    f"/projects/{self._project_id}/branches/{branch_id}/restore",
                    json={"source_branch_id": source_branch_id},
                )
        except httpx2.HTTPError as exc:
            raise NeonError("neon_unreachable") from exc
        if response.status_code >= 400:
            raise NeonError(f"restore_http_{response.status_code}")
        operations = response.json().get("operations", [])
        return [str(operation["id"]) for operation in operations if "id" in operation]

    async def wait_for_operations(
        self, operation_ids: list[str], *, timeout: float = 180.0, interval: float = 2.0
    ) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        pending = list(operation_ids)
        async with self._client() as client:
            while pending:
                if loop.time() > deadline:
                    raise NeonError("operations_timed_out")
                remaining: list[str] = []
                for operation_id in pending:
                    try:
                        response = await client.get(
                            f"/projects/{self._project_id}/operations/{operation_id}"
                        )
                    except httpx2.HTTPError as exc:
                        raise NeonError("neon_unreachable") from exc
                    if response.status_code >= 400:
                        raise NeonError(f"operation_http_{response.status_code}")
                    state = str(response.json().get("operation", {}).get("status", ""))
                    if state in FINISHED_STATES:
                        continue
                    if state in FAILED_STATES:
                        raise NeonError(f"operation_{state}")
                    remaining.append(operation_id)
                pending = remaining
                if pending:
                    await asyncio.sleep(interval)
