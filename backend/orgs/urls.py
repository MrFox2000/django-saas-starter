from django.urls import path

from .views import (
    CurrentOrgView,
    MemberDetailView,
    MemberListCreateView,
    OrgReportView,
    OrganizationListCreateView,
)

urlpatterns = [
    path("", OrganizationListCreateView.as_view(), name="organizations"),
    path("current/", CurrentOrgView.as_view(), name="current-org"),
    path("members/", MemberListCreateView.as_view(), name="members"),
    path("members/<int:pk>/", MemberDetailView.as_view(), name="member-detail"),
    path("report/", OrgReportView.as_view(), name="org-report"),
]
