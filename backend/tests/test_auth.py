"""Integration tests for authentication endpoints. Requires PostgreSQL
(see `conftest.requires_database`)."""
import pytest

from tests.conftest import requires_database

pytestmark = requires_database


@pytest.mark.asyncio
async def test_register_returns_token_pair(client, unique_email):
    response = await client.post(
        "/api/v1/auth/register", json={"email": unique_email, "password": "SuperSecret123"}
    )
    assert response.status_code == 201
    body = response.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_register_duplicate_email_is_rejected(client, unique_email):
    payload = {"email": unique_email, "password": "SuperSecret123"}
    first = await client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201

    second = await client.post("/api/v1/auth/register", json=payload)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_login_with_correct_credentials_succeeds(client, unique_email):
    await client.post("/api/v1/auth/register", json={"email": unique_email, "password": "SuperSecret123"})
    response = await client.post("/api/v1/auth/login", json={"email": unique_email, "password": "SuperSecret123"})
    assert response.status_code == 200
    assert "access_token" in response.json()


@pytest.mark.asyncio
async def test_login_with_wrong_password_is_rejected(client, unique_email):
    await client.post("/api/v1/auth/register", json={"email": unique_email, "password": "SuperSecret123"})
    response = await client.post("/api/v1/auth/login", json={"email": unique_email, "password": "WrongPassword"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_endpoint_requires_authentication(client):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_endpoint_returns_current_user(client, unique_email):
    register_response = await client.post(
        "/api/v1/auth/register", json={"email": unique_email, "password": "SuperSecret123"}
    )
    token = register_response.json()["access_token"]

    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == unique_email
