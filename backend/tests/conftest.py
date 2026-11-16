from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from billing import quota
from billing.models import Plan, Subscription
from orgs.models import Membership, Organization

PASSWORD = "test-pass-1234"


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def plan() -> Plan:
    return Plan.objects.get(code="starter")


def make_user(email: str, password: str = PASSWORD) -> User:
    return User.objects.create_user(email=email, password=password, full_name=email.split("@")[0])


def make_org(name: str, owner: User | None = None, plan_code: str = "free") -> Organization:
    organization = Organization.objects.create(name=name)
    if owner is not None:
        Membership.objects.create(
            organization=organization, user=owner, role=Membership.Role.OWNER
        )
    billing_plan = Plan.objects.get(code=plan_code)
    Subscription.objects.create(
        organization=organization,
        plan=billing_plan,
        status=Subscription.Status.ACTIVE,
    )
    return organization


def login(client: APIClient, email: str, password: str = PASSWORD) -> str:
    response = client.post(
        "/api/auth/token/", {"email": email, "password": password}, format="json"
    )
    assert response.status_code == 200, response.content
    return response.json()["access"]


def auth(client: APIClient, token: str) -> APIClient:
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def exhaust_quota(organization: Organization) -> None:
    plan = quota.get_plan(organization)
    quota.UsageRecord.objects.update_or_create(
        organization=organization,
        period=quota.current_period(),
        defaults={"api_calls": plan.monthly_api_calls},
    )
