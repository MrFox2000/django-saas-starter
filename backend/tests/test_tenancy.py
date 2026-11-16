from __future__ import annotations

import pytest

from billing import quota
from orgs.models import Membership

from .conftest import auth, exhaust_quota, make_org, make_user, login

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner_and_org(client):
    owner = make_user("owner@example.com")
    organization = make_org("Tenant A", owner=owner, plan_code="starter")
    return owner, organization, auth(client, login(client, owner.email))


def test_current_org_returns_members_and_quota(owner_and_org) -> None:
    _, organization, client = owner_and_org

    response = client.get("/api/orgs/current/")

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["organization"]["slug"] == organization.slug
    assert body["role"] == "owner"
    assert len(body["members"]) == 1
    assert body["quota"]["limit"] == 5000


def test_token_without_org_claim_is_rejected(client) -> None:
    make_user("noorg@example.com")
    token = login(client, "noorg@example.com")

    response = client.get("/api/orgs/current/", HTTP_AUTHORIZATION=f"Bearer {token}")

    assert response.status_code == 403


def test_member_of_one_org_cannot_reach_another(owner_and_org) -> None:
    _, _, client = owner_and_org

    outsider = make_user("outsider@example.com")
    other = make_org("Tenant B", owner=outsider)

    response = client.post(
        "/api/auth/switch-org/", {"org_id": other.pk}, format="json"
    )

    assert response.status_code == 403
    assert "not a member" in response.json()["detail"]


def test_switch_org_reissues_a_scoped_token(client) -> None:
    user = make_user("both@example.com")
    first = make_org("First", owner=user)
    second = make_org("Second", owner=user)
    scoped = auth(client, login(client, user.email))

    response = scoped.post("/api/auth/switch-org/", {"org_id": second.pk}, format="json")

    assert response.status_code == 200
    body = response.json()
    assert body["org"]["id"] == second.pk

    switched = auth(client, body["access"])
    current = switched.get("/api/orgs/current/").json()
    assert current["organization"]["id"] == second.pk


def test_member_cannot_invite(owner_and_org) -> None:
    _, organization, client = owner_and_org
    member_user = make_user("member@example.com")
    Membership.objects.create(
        organization=organization, user=member_user, role=Membership.Role.MEMBER
    )
    member_client = auth(client, login(client, member_user.email))

    response = member_client.post(
        "/api/orgs/members/", {"email": "newbie@example.com"}, format="json"
    )

    assert response.status_code == 403


def test_admin_can_invite_existing_user(owner_and_org) -> None:
    _, organization, client = owner_and_org
    admin_user = make_user("admin@example.com")
    Membership.objects.create(
        organization=organization, user=admin_user, role=Membership.Role.ADMIN
    )
    make_user("newbie@example.com")
    admin_client = auth(client, login(client, admin_user.email))

    response = admin_client.post(
        "/api/orgs/members/", {"email": "newbie@example.com", "role": "member"}, format="json"
    )

    assert response.status_code == 201, response.content
    assert response.json()["email"] == "newbie@example.com"


def test_invite_unknown_email_is_refused(owner_and_org) -> None:
    _, _, client = owner_and_org

    response = client.post(
        "/api/orgs/members/", {"email": "ghost@example.com"}, format="json"
    )

    assert response.status_code == 400


def test_seat_limit_is_enforced(client) -> None:
    owner = make_user("seatowner@example.com")
    make_org("Tiny", owner=owner, plan_code="free")  # free plan: 1 seat
    owner_client = auth(client, login(client, owner.email))
    make_user("extra@example.com")

    response = owner_client.post(
        "/api/orgs/members/", {"email": "extra@example.com"}, format="json"
    )

    assert response.status_code == 400
    assert "seat" in str(response.json()).lower()


def test_owner_cannot_be_removed(owner_and_org) -> None:
    _, organization, client = owner_and_org
    membership = organization.memberships.get()

    response = client.delete(f"/api/orgs/members/{membership.pk}/")

    assert response.status_code == 400


def test_metred_report_consumes_one_call(owner_and_org) -> None:
    _, organization, client = owner_and_org
    before = quota.usage_for(organization)

    response = client.post("/api/orgs/report/")

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["quota"]["used"] == before + 1
    assert quota.usage_for(organization) == before + 1


def test_report_returns_402_when_quota_is_spent(owner_and_org) -> None:
    _, organization, client = owner_and_org
    exhaust_quota(organization)

    response = client.post("/api/orgs/report/")

    assert response.status_code == 402
    body = response.json()
    assert body["upgrade_required"] is True
    assert body["used"] == body["limit"]
