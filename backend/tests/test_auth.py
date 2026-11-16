from __future__ import annotations

import pytest

from accounts.models import User
from orgs.models import Membership, Organization

from .conftest import PASSWORD, login, make_user

pytestmark = pytest.mark.django_db


def test_register_creates_user_org_and_ownership(client) -> None:
    response = client.post(
        "/api/auth/register/",
        {
            "email": "Founder@Example.com",
            "full_name": "Founder",
            "password": PASSWORD,
            "organization_name": "Founder Labs",
        },
        format="json",
    )

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["user"]["email"] == "founder@example.com"
    assert body["access"] and body["refresh"]

    membership = Membership.objects.get(user__email="founder@example.com")
    assert membership.organization.name == "Founder Labs"
    assert membership.role == Membership.Role.OWNER


def test_register_defaults_the_org_name(client) -> None:
    response = client.post(
        "/api/auth/register/",
        {"email": "solo@example.com", "password": PASSWORD},
        format="json",
    )

    assert response.status_code == 201
    organization = Organization.objects.get(memberships__user__email="solo@example.com")
    assert "solo" in organization.name.lower()


def test_register_rejects_duplicate_email(client) -> None:
    make_user("taken@example.com")

    response = client.post(
        "/api/auth/register/",
        {"email": "taken@example.com", "password": PASSWORD},
        format="json",
    )

    assert response.status_code == 400
    assert "email" in response.json()


def test_register_rejects_short_password(client) -> None:
    response = client.post(
        "/api/auth/register/",
        {"email": "short@example.com", "password": "abc"},
        format="json",
    )

    assert response.status_code == 400


def test_token_contains_the_active_organisation(client) -> None:
    client.post(
        "/api/auth/register/",
        {"email": "jwt@example.com", "password": PASSWORD, "organization_name": "JWT Inc"},
        format="json",
    )

    response = client.post(
        "/api/auth/token/", {"email": "jwt@example.com", "password": PASSWORD}, format="json"
    )

    body = response.json()
    assert body["org"]["name"] == "JWT Inc"
    assert body["org"]["role"] == "owner"

    from rest_framework_simplejwt.tokens import AccessToken

    token = AccessToken(body["access"])
    assert token["org_id"] == body["org"]["id"]


def test_me_lists_memberships(client) -> None:
    make_user("me@example.com")
    token = login(client, "me@example.com")

    response = client.get("/api/auth/me/", HTTP_AUTHORIZATION=f"Bearer {token}")

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["user"]["email"] == "me@example.com"
    assert isinstance(body["organizations"], list)


def test_me_requires_authentication(client) -> None:
    assert client.get("/api/auth/me/").status_code == 401


def test_user_model_is_email_based(client) -> None:
    user = User.objects.create_user(email="Upper@Example.COM", password=PASSWORD)

    assert user.email == "upper@example.com"
    assert user.USERNAME_FIELD == "email"
