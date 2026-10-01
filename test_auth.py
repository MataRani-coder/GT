"""Minimal RBAC smoke test for Ghost Trail authentication."""
import os
os.environ.setdefault("GHOST_TRAIL_ADMIN_USERNAME", "smokeadmin")
os.environ.setdefault("GHOST_TRAIL_ADMIN_PASSWORD", "SmokePass123!")
from fastapi.testclient import TestClient
import sentinel_server as server

client = TestClient(server.app)
assert client.get("/api/cameras").status_code == 401
login = client.post("/api/auth/login", json={"username": os.environ["GHOST_TRAIL_ADMIN_USERNAME"], "password": os.environ["GHOST_TRAIL_ADMIN_PASSWORD"]})
assert login.status_code == 200, login.text
token = login.json()["token"]
headers = {"Authorization": f"Bearer {token}"}
assert client.get("/api/cameras", headers=headers).status_code == 200
assert client.get("/api/audit", headers=headers).status_code == 200
assert client.get("/api/cameras", headers={"Authorization": "Bearer invalid"}).status_code == 401
print("AUTH/RBAC SMOKE TEST: PASS")
