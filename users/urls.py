from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"users", views.UserViewSet, basename="user")

urlpatterns = [
    path("login/", views.login),
    path("me/", views.me),
] + router.urls
