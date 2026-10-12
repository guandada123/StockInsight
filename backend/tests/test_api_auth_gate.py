"""P1-5 访问闸门测试（api_auth_gate，2026-10-12）。

审计原状：`backend/main.py` 只有 CORS、**无任何鉴权**（缓解项仅是容器绑 127.0.0.1）。
新增闸门的两档语义必须被钉死，否则"以为加了鉴权"比没加更危险：

  ① 配了 `SI_API_TOKEN` → 缺头/错头一律 401，对了才放行；
  ② 未配 token → **只允许本机**（127.0.0.1 / ::1 / localhost）；非本机 401；
  ③ `/api/health` 免检（监控探针无凭据可用）；
  ④ 未来若要在局域网开放 → **必须先配 token 再改绑定**（顺序反了就是无鉴权暴露）。

测试手法：TestClient 的 `client.host` 是 `"testclient"`（**非本机**），
正好天然充当"外部请求"，无需伪造 IP；要模拟本机请求则覆盖 `client` 属性。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402

TOKEN_ENV = "SI_API_TOKEN"  # noqa: S105 —— 这是**环境变量名**，不是口令值（bandit 按变量名误报）


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """每个用例都从"未配 token"的干净态出发，避免用例间互相污染。"""
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    yield
    os.environ.pop(TOKEN_ENV, None)


def _client(from_host: str | None = None) -> TestClient:
    """from_host 非空时模拟"来自该地址的请求"（Starlette TestClient 的 client= 参数）。"""
    if from_host:
        return TestClient(app, client=(from_host, 43210))
    return TestClient(app)


# ────────────────────────────────────────────────
# ① 配置了 token：必须带头且正确
# ────────────────────────────────────────────────


def test_with_token_missing_header_is_401(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, "s3cret")
    r = _client().get("/api/market/indices")
    assert r.status_code == 401, f"配了 token 却无头放行 = 鉴权形同虚设（{r.status_code}）"
    assert "unauthorized" in r.json()["detail"]


def test_with_token_wrong_header_is_401(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, "s3cret")
    r = _client().get("/api/market/indices", headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_with_token_correct_header_passes_gate(monkeypatch):
    """正确的 token 必须能过闸门（不要求业务成功，只要求**不是 401**）。"""
    monkeypatch.setenv(TOKEN_ENV, "s3cret")
    r = _client().get("/api/market/indices", headers={"X-API-Key": "s3cret"})
    assert r.status_code != 401, f"正确凭据被拦 = 闸门配错（{r.status_code}）"


# ────────────────────────────────────────────────
# ② 未配 token：只允许本机
# ────────────────────────────────────────────────


def test_without_token_external_client_is_401():
    """TestClient 的 host 是 "testclient"（非本机）→ 未配 token 时必须 401。"""
    r = _client().get("/api/market/indices")
    assert r.status_code == 401, "未配 token 却放行非本机请求 = 无鉴权暴露"
    assert "仅允许本机" in r.json()["detail"]


def test_without_token_local_client_passes_gate():
    """把 client.host 伪装成 127.0.0.1 → 应放行（本机不要求凭据）。"""
    r = _client(from_host="127.0.0.1").get("/api/market/indices")
    assert r.status_code != 401, f"本机请求被拦 = 正常链路被误伤（{r.status_code}）"


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost"])
def test_localhost_variants_all_allowed(host):
    assert _client(from_host=host).get("/api/market/indices").status_code != 401


# ────────────────────────────────────────────────
# ③ /api/health 免检
# ────────────────────────────────────────────────


def test_health_is_exempt_without_token():
    r = _client().get("/api/health")
    assert r.status_code == 200, "健康探针被鉴权拦掉 = 监控失明"


def test_health_is_exempt_with_token_configured(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, "s3cret")
    assert _client().get("/api/health").status_code == 200
