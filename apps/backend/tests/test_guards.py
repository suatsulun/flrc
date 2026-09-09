import pytest

MATRIX = [
    ("GET", "/api/healthz", None, 204),
    ("GET", "/api/me", None, 401),
    ("GET", "/api/admin/ping", None, 401),
    ("GET", "/api/admin/ping", "teacher", 403),
    ("GET", "/api/admin/ping", "coordinator", 403),
    ("GET", "/api/admin/ping", "admin", 200),
    ("GET", "/api/columns?grade_level=5&subject=english", None, 401),
    ("GET", "/api/columns?grade_level=5&subject=english", "teacher", 403),
    ("GET", "/api/columns?grade_level=5&subject=english", "coordinator", 403),
]


@pytest.mark.parametrize("method, path, role, expected", MATRIX)
async def test_matrix(client_as, method, path, role, expected):
    async with client_as(role) as client:
        response = await client.request(method, path)
    assert response.status_code == expected
