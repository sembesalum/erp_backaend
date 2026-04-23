import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, viewsets
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.decorators import action, api_view
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from users.models import User

from .permissions import IsAdminRole
from .models import (
    AuditLog,
    Driver,
    FuelPrice,
    FuelRequest,
    FuelStation,
    OperationActivity,
    RequestTimelineEvent,
    Vehicle,
)
from .serializers import (
    AuditLogSerializer,
    DriverSerializer,
    FuelPriceSerializer,
    FuelRequestDetailSerializer,
    FuelRequestListSerializer,
    FuelRequestSerializer,
    FuelRequestUpdateSerializer,
    FuelStationSerializer,
    OperationActivitySerializer,
    RequestTimelineEventSerializer,
    VehicleSerializer,
)


@api_view(["GET"])
def health(_request):
    return Response({"status": "ok", "service": "synarete-fuel-api"})


class FuelStationViewSet(viewsets.ModelViewSet):
    """
    List/retrieve: public (e.g. mobile app station picker).
    Create/update/delete: admin only (ERP dashboard with token).
    """

    queryset = FuelStation.objects.all()
    serializer_class = FuelStationSerializer
    authentication_classes = [TokenAuthentication]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["is_active", "region"]
    search_fields = ["name", "region", "address"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [AllowAny()]
        return [IsAuthenticated(), IsAdminRole()]


class DriverFilter(django_filters.FilterSet):
    class Meta:
        model = Driver
        fields = ["assigned_station", "is_active"]


class DriverViewSet(viewsets.ModelViewSet):
    queryset = (
        Driver.objects.select_related("user", "assigned_station")
        .prefetch_related("vehicles")
        .all()
    )
    serializer_class = DriverSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsAdminRole]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = DriverFilter
    search_fields = ["user__email", "user__full_name", "license_number"]


class VehicleFilter(django_filters.FilterSet):
    class Meta:
        model = Vehicle
        fields = ["driver", "is_active", "default_fuel_type"]


class VehicleViewSet(viewsets.ModelViewSet):
    queryset = Vehicle.objects.select_related("driver", "driver__user").all()
    serializer_class = VehicleSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsAdminRole]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = VehicleFilter
    search_fields = ["plate", "make", "model"]


class FuelPriceFilter(django_filters.FilterSet):
    class Meta:
        model = FuelPrice
        fields = ["station", "fuel_type"]


class FuelPriceViewSet(viewsets.ModelViewSet):
    queryset = FuelPrice.objects.select_related("station", "set_by").all()
    serializer_class = FuelPriceSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = FuelPriceFilter
    ordering_fields = ["effective_from", "created_at"]
    ordering = ["-effective_from"]


class FuelRequestFilter(django_filters.FilterSet):
    reference = django_filters.CharFilter(field_name="reference", lookup_expr="iexact")

    class Meta:
        model = FuelRequest
        fields = ["mvfo_status", "status", "station", "driver", "fuel_type", "reference"]


class FuelRequestViewSet(viewsets.ModelViewSet):
    queryset = (
        FuelRequest.objects.select_related("driver", "driver__user", "station", "vehicle")
        .prefetch_related("timeline_events", "driver__vehicles")
        .all()
    )
    authentication_classes = [TokenAuthentication]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = FuelRequestFilter
    search_fields = ["reference", "notes", "driver__user__full_name"]
    ordering_fields = ["request_datetime", "created_at", "updated_at"]
    ordering = ["-request_datetime"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return FuelRequest.objects.none()
        role = getattr(user, "role", None)
        if role == User.Role.ADMIN:
            return qs
        if role in (User.Role.APPROVER, User.Role.QSE):
            return qs
        if role == User.Role.SIMBA_OIL:
            if user.assigned_station_id:
                return qs.filter(station_id=user.assigned_station_id)
            return qs.none()
        if role == User.Role.DRIVER:
            try:
                return qs.filter(driver=user.driver_profile)
            except Driver.DoesNotExist:
                return qs.none()
        return qs.none()

    def get_serializer_class(self):
        if self.action == "list":
            return FuelRequestListSerializer
        if self.action == "retrieve":
            return FuelRequestDetailSerializer
        if self.action in ("update", "partial_update"):
            return FuelRequestUpdateSerializer
        return FuelRequestSerializer

    def perform_create(self, serializer):
        user = self.request.user
        role = getattr(user, "role", None)
        if role == User.Role.ADMIN:
            serializer.save()
            return
        if role != User.Role.DRIVER:
            raise PermissionDenied("Only drivers can create MVFO requests from the app.")
        try:
            profile = user.driver_profile
        except Driver.DoesNotExist:
            raise PermissionDenied("No driver profile for this account.")
        driver = serializer.validated_data.get("driver")
        if driver is None or driver.pk != profile.pk:
            raise PermissionDenied("You can only create requests for your own driver profile.")
        serializer.save()

    def perform_update(self, serializer):
        user = self.request.user
        instance = serializer.instance
        role = getattr(user, "role", None)
        new_mvfo = serializer.validated_data.get("mvfo_status", instance.mvfo_status)

        if role == User.Role.ADMIN:
            serializer.save()
            return

        if role in (User.Role.APPROVER, User.Role.QSE):
            if instance.mvfo_status != FuelRequest.MvfoStatus.CREATED:
                raise PermissionDenied("This MVFO is no longer awaiting QSE review.")
            if new_mvfo not in (
                FuelRequest.MvfoStatus.APPROVED,
                FuelRequest.MvfoStatus.REJECTED,
            ):
                raise PermissionDenied("QSE can only approve or reject CREATED requests.")
            serializer.save()
            return

        if role == User.Role.SIMBA_OIL:
            if not user.assigned_station_id or user.assigned_station_id != instance.station_id:
                raise PermissionDenied("You are not assigned to this station.")
            if instance.mvfo_status in (
                FuelRequest.MvfoStatus.CREATED,
                FuelRequest.MvfoStatus.REJECTED,
            ):
                raise PermissionDenied("Station staff act after QSE approval.")
            serializer.save()
            return

        raise PermissionDenied("You cannot update this MVFO.")

    @action(detail=True, methods=["post"], url_path="submit-driver-proof")
    def submit_driver_proof(self, request, pk=None):
        """Driver submits completion proof after station sets mvfo_status to COLLECTED."""
        fuel_request = self.get_object()
        user = request.user
        role = getattr(user, "role", None)
        if role != User.Role.DRIVER:
            raise PermissionDenied("Only drivers can submit EFD receipt proof.")
        try:
            profile = user.driver_profile
        except Driver.DoesNotExist:
            raise PermissionDenied("No driver profile for this account.")
        if fuel_request.driver_id != profile.pk:
            raise PermissionDenied("You can only submit proof for your own MVFOs.")
        if fuel_request.mvfo_status != FuelRequest.MvfoStatus.COLLECTED:
            raise ValidationError(
                {
                    "detail": (
                        "EFD receipt can only be submitted when the order is COLLECTED "
                        "(after the station has finished dispensing)."
                    ),
                },
            )
        efd = (request.data.get("efd_receipt_base64") or "").strip()
        odo = (request.data.get("odometer_photo_base64") or "").strip()
        driver_pump = (request.data.get("driver_pump_photo_base64") or "").strip()
        if not efd:
            raise ValidationError({"efd_receipt_base64": "EFD receipt image is required."})
        if not odo:
            raise ValidationError({"odometer_photo_base64": "Odometer photo is required."})
        if (fuel_request.efd_receipt_base64 or "").strip() and (fuel_request.odometer_photo_base64 or "").strip():
            raise ValidationError(
                {"detail": "Driver proof has already been submitted for this MVFO."},
            )
        fuel_request.efd_receipt_base64 = efd
        fuel_request.odometer_photo_base64 = odo
        if driver_pump:
            fuel_request.driver_pump_photo_base64 = driver_pump
        fuel_request.mvfo_status = FuelRequest.MvfoStatus.COMPLETED
        fuel_request.status = FuelRequest.LegacyStatus.COMPLETED
        fuel_request.save(
            update_fields=[
                "efd_receipt_base64",
                "odometer_photo_base64",
                "driver_pump_photo_base64",
                "mvfo_status",
                "status",
                "updated_at",
            ],
        )
        serializer = FuelRequestSerializer(fuel_request, context={"request": request})
        return Response(serializer.data)

    @action(detail=True, methods=["get", "post"])
    def timeline(self, request, pk=None):
        fuel_request = self.get_object()
        if request.method == "GET":
            qs = fuel_request.timeline_events.all()
            ser = RequestTimelineEventSerializer(qs, many=True)
            return Response(ser.data)
        ser = RequestTimelineEventSerializer(data={**request.data, "fuel_request": fuel_request.pk})
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=201)


class AuditLogViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    filterset_fields = ["action", "role"]


class OperationActivityViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = OperationActivity.objects.all()
    serializer_class = OperationActivitySerializer
    filterset_fields = ["category", "role"]
