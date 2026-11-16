from django.urls import path

from .views import CancelView, CheckoutView, PlanListView, StripeWebhookView, SubscriptionView

urlpatterns = [
    path("plans/", PlanListView.as_view(), name="plans"),
    path("subscription/", SubscriptionView.as_view(), name="subscription"),
    path("checkout/", CheckoutView.as_view(), name="checkout"),
    path("cancel/", CancelView.as_view(), name="cancel"),
    path("webhook/", StripeWebhookView.as_view(), name="stripe-webhook"),
]
