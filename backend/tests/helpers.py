from fastapi.testclient import TestClient


def csrf_headers(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("vsf_csrf")
    assert token
    return {"X-CSRF-Token": token}
