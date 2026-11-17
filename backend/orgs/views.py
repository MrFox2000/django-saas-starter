"""Organisation endpoints, including the metered report."""

from __future__ import annotations

from django.db.models import Count
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import ListCreateAPIView, get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from billing import quota
from billing.models import Subscription
from billing.providers import get_provider
from billing.serializers import SubscriptionSerializer

from .models import Membership, Organization
from .permissions import HasOrganization, IsOrgAdmin
from .serializers import (
    CurrentOrgSerializer,
    MemberCreateSerializer,
    MemberRoleSerializer,
    MemberSerializer,
    OrganizationSerializer,
    OrgReportSerializer,
)


class OrganizationListCreateView(ListCreateAPIView):
    """List the organisations you belong to, or create a new one."""

    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Organization.objects.filter(memberships__user=self.request.user)
            .distinct()
            .order_by("name")
        )

    def perform_create(self, serializer):
        organization = serializer.save()
        Membership.objects.create(
            organization=organization, user=self.request.user, role=Membership.Role.OWNER
        )


class CurrentOrgView(APIView):
    """Everything the dashboard needs about the active organisation."""

    permission_classes = [HasOrganization]

    @extend_schema(responses=CurrentOrgSerializer)
    def get(self, request):
        organization = request.organization
        subscription = Subscription.objects.select_related("plan").filter(
            organization=organization
        ).first()
        return Response(
            {
                "organization": OrganizationSerializer(organization, context={"request": request}).data,
                "role": request.membership.role,
                "members": MemberSerializer(
                    organization.memberships.select_related("user").order_by("created_at"), many=True
                ).data,
                "subscription": SubscriptionSerializer(subscription).data if subscription else None,
                "quota": vars(quota.quota_state(organization)),
            }
        )


class MemberListCreateView(APIView):
    permission_classes = [HasOrganization]

    @extend_schema(responses=MemberSerializer(many=True))
    def get(self, request):
        members = request.organization.memberships.select_related("user").order_by("created_at")
        return Response(MemberSerializer(members, many=True).data)

    @extend_schema(request=MemberCreateSerializer, responses={201: MemberSerializer})
    def post(self, request):
        if not request.membership.is_admin:
            return Response(
                {"detail": "Only owners and admins can invite members."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = MemberCreateSerializer(
            data=request.data, context={"organization": request.organization}
        )
        serializer.is_valid(raise_exception=True)
        membership = Membership.objects.create(
            organization=request.organization,
            user=serializer.validated_data["user"],
            role=serializer.validated_data["role"],
        )
        return Response(MemberSerializer(membership).data, status=status.HTTP_201_CREATED)


class MemberDetailView(APIView):
    permission_classes = [IsOrgAdmin]

    @extend_schema(request=MemberRoleSerializer, responses=MemberSerializer)
    def patch(self, request, pk: int):
        membership = get_object_or_404(
            request.organization.memberships.select_related("user"), pk=pk
        )
        serializer = MemberRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if (
            membership.role == Membership.Role.OWNER
            and serializer.validated_data["role"] != Membership.Role.OWNER
        ):
            return Response(
                {"detail": "Transfer ownership instead of demoting the owner."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        membership.role = serializer.validated_data["role"]
        membership.save(update_fields=["role"])
        return Response(MemberSerializer(membership).data)

    @extend_schema(request=None, responses={204: None})
    def delete(self, request, pk: int):
        membership = get_object_or_404(request.organization.memberships, pk=pk)
        if membership.role == Membership.Role.OWNER:
            return Response(
                {"detail": "The owner cannot be removed."}, status=status.HTTP_400_BAD_REQUEST
            )
        membership.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class OrgReportView(APIView):
    """A genuinely metered endpoint: it does work and spends one call from the plan."""

    permission_classes = [HasOrganization]

    @extend_schema(request=None, responses={200: OrgReportSerializer})
    def post(self, request):
        try:
            state = quota.consume(request.organization, amount=1)
        except quota.QuotaExceeded as exc:
            return Response(
                {
                    "detail": str(exc),
                    "used": exc.used,
                    "limit": exc.limit,
                    "plan": exc.plan.code,
                    "upgrade_required": True,
                },
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        organization = request.organization
        roles = organization.memberships.values("role").annotate(total=Count("id"))
        return Response(
            {
                "generated_at": quota.current_period().isoformat(),
                "organization": organization.name,
                "member_count": organization.memberships.count(),
                "roles": {row["role"]: row["total"] for row in roles},
                "quota": vars(state),
                "provider": get_provider().name,
            }
        )
