"""Auth endpoints: register, token, refresh, me, switch organisation."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from orgs.models import Membership

from .serializers import (
    MeSerializer,
    RegisterResponseSerializer,
    RegisterSerializer,
    SwitchOrgRequestSerializer,
    SwitchOrgResponseSerializer,
    UserSerializer,
)


class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    @extend_schema(request=RegisterSerializer, responses={201: RegisterResponseSerializer})
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        refresh = RefreshToken.for_user(user)
        membership = Membership.objects.filter(user=user).select_related("organization").first()
        if membership:
            refresh["org_id"] = membership.organization_id
            refresh["org_slug"] = membership.organization.slug
            refresh["role"] = membership.role

        return Response(
            {
                "user": UserSerializer(user).data,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_201_CREATED,
        )


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=MeSerializer)
    def get(self, request):
        memberships = (
            Membership.objects.filter(user=request.user)
            .select_related("organization")
            .order_by("created_at")
        )
        return Response(
            {
                "user": UserSerializer(request.user).data,
                "organizations": [
                    {
                        "id": membership.organization_id,
                        "name": membership.organization.name,
                        "slug": membership.organization.slug,
                        "role": membership.role,
                    }
                    for membership in memberships
                ],
                "active_org_id": getattr(request.auth, "get", lambda *_: None)("org_id"),
            }
        )


class SwitchOrgView(APIView):
    """Issues a fresh access token scoped to another organisation the caller belongs to."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=SwitchOrgRequestSerializer, responses={200: SwitchOrgResponseSerializer})
    def post(self, request):
        org_id = request.data.get("org_id")
        membership = (
            Membership.objects.filter(user=request.user, organization_id=org_id)
            .select_related("organization")
            .first()
        )
        if membership is None:
            return Response(
                {"detail": "You are not a member of that organisation."},
                status=status.HTTP_403_FORBIDDEN,
            )

        refresh = RefreshToken.for_user(request.user)
        refresh["org_id"] = membership.organization_id
        refresh["org_slug"] = membership.organization.slug
        refresh["role"] = membership.role

        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "org": {
                    "id": membership.organization_id,
                    "name": membership.organization.name,
                    "slug": membership.organization.slug,
                    "role": membership.role,
                },
            }
        )


class RefreshView(TokenRefreshView):
    permission_classes = [AllowAny]
