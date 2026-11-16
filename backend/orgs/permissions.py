"""Permissions derived from the `org_id` claim inside the access token.

The tenant is part of the token, not of the URL. That means a client cannot
reach another organisation by editing a path segment: the only organisations a
token can address are the ones the user is actually a member of.
"""

from __future__ import annotations

from rest_framework.permissions import BasePermission

from .models import Membership


class HasOrganization(BasePermission):
    """Resolve `request.membership` from the token, or reject the request."""

    message = "No organisation selected. Sign in again or switch organisation."

    def has_permission(self, request, view) -> bool:
        payload = getattr(request, "auth", None)
        user = getattr(request, "user", None)
        if payload is None or user is None or not user.is_authenticated:
            return False

        org_id = payload.get("org_id") if hasattr(payload, "get") else None
        if not org_id:
            return False

        membership = (
            Membership.objects.select_related("organization", "user")
            .filter(user=user, organization_id=org_id, organization__is_active=True)
            .first()
        )
        if membership is None:
            return False

        request.membership = membership
        request.organization = membership.organization
        return True


class IsOrgAdmin(HasOrganization):
    message = "Only owners and admins of this organisation can do that."

    def has_permission(self, request, view) -> bool:
        return super().has_permission(request, view) and request.membership.is_admin


class IsOrgOwner(HasOrganization):
    message = "Only the owner of this organisation can do that."

    def has_permission(self, request, view) -> bool:
        return (
            super().has_permission(request, view)
            and request.membership.role == Membership.Role.OWNER
        )
