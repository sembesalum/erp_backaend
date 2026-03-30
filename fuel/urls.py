from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"stations", views.FuelStationViewSet, basename="fuelstation")
router.register(r"drivers", views.DriverViewSet, basename="driver")
router.register(r"vehicles", views.VehicleViewSet, basename="vehicle")
router.register(r"fuel-prices", views.FuelPriceViewSet, basename="fuelprice")
router.register(r"fuel-requests", views.FuelRequestViewSet, basename="fuelrequest")
router.register(r"audit-logs", views.AuditLogViewSet, basename="auditlog")
router.register(r"operation-activities", views.OperationActivityViewSet, basename="operationactivity")

urlpatterns = [
    path("health/", views.health),
    path("", include(router.urls)),
]
