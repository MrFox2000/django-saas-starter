from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView

from .views import MeView, RefreshView, RegisterView, SwitchOrgView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", RefreshView.as_view(), name="token_refresh"),
    path("me/", MeView.as_view(), name="me"),
    path("switch-org/", SwitchOrgView.as_view(), name="switch_org"),
]
