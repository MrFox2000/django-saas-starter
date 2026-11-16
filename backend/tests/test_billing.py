from __future__ import annotations

import pytest

from billing import quota
from billing.models import Plan, Subscription

from .conftest import auth, exhaust_quota, login, make_org, make_user

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner_client(client):
    owner = make_user("billing@example.com")
    organization = make_org("Billing Co", owner=owner, plan_code="free")
    return organization, auth(client, login(client, owner.email))


def test_plans_are_public(client) -> None:
    response = client.get("/api/billing/plans/")

    assert response.status_code == 200
    codes = [plan["code"] for plan in response.json()]
    assert codes == ["free", "starter", "pro"]


def test_subscription_reports_quota_and_provider(owner_client) -> None:
    _, client = owner_client

    body = client.get("/api/billing/subscription/").json()

    assert body["subscription"]["plan"]["code"] == "free"
    assert body["quota"]["limit"] == 100
    assert body["provider"] == "fake"


def test_checkout_activates_the_new_plan(owner_client) -> None:
    organization, client = owner_client

    response = client.post("/api/billing/checkout/", {"plan_code": "pro"}, format="json")

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["provider"] == "fake"
    assert "plan=pro" in body["checkout_url"]

    subscription = Subscription.objects.get(organization=organization)
    assert subscription.plan.code == "pro"
    assert subscription.status == Subscription.Status.ACTIVE
    assert quota.quota_state(organization).limit == 50_000


def test_checkout_rejects_unknown_plan(owner_client) -> None:
    _, client = owner_client

    response = client.post("/api/billing/checkout/", {"plan_code": "enterprise"}, format="json")

    assert response.status_code == 404


def test_upgrading_lifts_an_exhausted_quota(owner_client) -> None:
    organization, client = owner_client
    exhaust_quota(organization)
    assert client.post("/api/orgs/report/").status_code == 402

    client.post("/api/billing/checkout/", {"plan_code": "starter"}, format="json")

    assert client.post("/api/orgs/report/").status_code == 200


def test_cancel_sets_status(owner_client) -> None:
    organization, client = owner_client

    response = client.post("/api/billing/cancel/")

    assert response.status_code == 200
    assert Subscription.objects.get(organization=organization).status == "canceled"


def test_quota_consume_raises_when_full(owner_client) -> None:
    organization, _ = owner_client
    exhaust_quota(organization)

    with pytest.raises(quota.QuotaExceeded):
        quota.consume(organization)


def test_quota_state_starts_at_zero(owner_client) -> None:
    organization, _ = owner_client

    state = quota.quota_state(organization)

    assert state.used == 0
    assert state.remaining == 100


def test_webhook_activates_subscription_without_secret(client, settings) -> None:
    settings.STRIPE_WEBHOOK_SECRET = ""
    owner = make_user("hook@example.com")
    organization = make_org("Hook Co", owner=owner, plan_code="free")
    plan = Plan.objects.get(code="pro")

    payload = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": str(organization.pk),
                "metadata": {"plan_code": plan.code},
                "subscription": "sub_123",
            }
        },
    }

    response = client.post("/api/billing/webhook/", payload, format="json")

    assert response.status_code == 200
    subscription = Subscription.objects.get(organization=organization)
    assert subscription.plan.code == "pro"
    assert subscription.status == Subscription.Status.ACTIVE


def test_webhook_ignores_other_events(client) -> None:
    response = client.post("/api/billing/webhook/", {"type": "invoice.paid"}, format="json")

    assert response.status_code == 200
