import logging

import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status, viewsets
from rest_framework.authentication import TokenAuthentication
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.decorators import action, api_view
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from users.models import User

from .permissions import IsAdminRole
from .s3_uploads import upload_request_image
from .models import (
    AuditLog,
    Driver,
    FuelPrice,
    FuelRequest,
    FuelStation,
    OperationActivity,
    RequestTimelineEvent,
    SystemSettings,
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
    SystemSettingsSerializer,
    VehicleSerializer,
)

logger = logging.getLogger(__name__)


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

    @action(detail=True, methods=["post"], url_path="delete")
    def delete_vehicle(self, request, pk=None):
        """Hard-delete via POST so dashboards work behind proxies that block HTTP DELETE."""
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


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
    parser_classes = [JSONParser, MultiPartParser, FormParser]

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
        station = serializer.validated_data.get("station")
        if station is not None and profile.assigned_station_id and station.pk != profile.assigned_station_id:
            notes = (serializer.validated_data.get("notes") or "").strip()
            if len(notes) < 5:
                serializer.validated_data["notes"] = (
                    f"Station override reason: Auto-captured (assigned station "
                    f"{profile.assigned_station_id}, requested station {station.pk})."
                )
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
            if instance.mvfo_status != FuelRequest.MvfoStatus.APPROVED:
                raise PermissionDenied("Station staff can only act on APPROVED requests.")
            if new_mvfo not in (
                FuelRequest.MvfoStatus.ACCEPTED,
                FuelRequest.MvfoStatus.REJECTED,
            ):
                raise PermissionDenied("Station staff can only approve or reject requests.")
            serializer.save()
            return

        raise PermissionDenied("You cannot update this MVFO.")

    @action(detail=True, methods=["post"], url_path="upload-evidence")
    def upload_evidence(self, request, pk=None):
        """Upload one image to S3 and store only the returned URL."""
        fuel_request = self.get_object()
        user = request.user
        kind = (request.data.get("kind") or "").strip()
        file_obj = request.FILES.get("image")
        if not file_obj:
            raise ValidationError({"image": "Image file is required."})
        field_map = {
            "pump_meter_photo": "pump_meter_photo_url",
            "fuel_level_photo": "fuel_level_photo_url",
            "efd_receipt": "efd_receipt_url",
            "odometer_photo": "odometer_photo_url",
            "driver_pump_photo": "driver_pump_photo_url",
        }
        target_field = field_map.get(kind)
        if not target_field:
            raise ValidationError({"kind": f"Invalid kind. Allowed: {', '.join(field_map.keys())}"})
        role = getattr(user, "role", None)
        if kind == "pump_meter_photo" and role not in (User.Role.ADMIN, User.Role.SIMBA_OIL):
            raise PermissionDenied("Only station staff/admin can upload pump meter photo.")
        if kind != "pump_meter_photo" and role not in (User.Role.ADMIN, User.Role.DRIVER):
            raise PermissionDenied("Only driver/admin can upload this proof image.")

        object_key, image_url = upload_request_image(
            file_obj,
            reference=fuel_request.reference or f"request-{fuel_request.pk}",
            image_kind=kind,
        )
        setattr(fuel_request, target_field, image_url)
        update_fields = [target_field, "updated_at"]
        if target_field == "pump_meter_photo_url":
            fuel_request.has_pump_meter_photo = True
            update_fields.append("has_pump_meter_photo")
        fuel_request.save(update_fields=update_fields)
        return Response(
            {
                "reference": fuel_request.reference,
                "kind": kind,
                "s3_key": object_key,
                "url": image_url,
            },
            status=201,
        )

    @action(detail=True, methods=["post"], url_path="submit-driver-proof")
    def submit_driver_proof(self, request, pk=None):
        """Driver submits completion proof after station sets mvfo_status to COLLECTED."""
        fuel_request = self.get_object()
        user = request.user
        role = getattr(user, "role", None)
        logger.info(
            "submit_driver_proof attempt request_id=%s user_id=%s role=%s mvfo_status=%s files=%s",
            fuel_request.pk,
            getattr(user, "id", None),
            role,
            fuel_request.mvfo_status,
            list(request.FILES.keys()),
        )
        if role != User.Role.DRIVER:
            logger.warning(
                "submit_driver_proof denied non-driver request_id=%s user_id=%s role=%s",
                fuel_request.pk,
                getattr(user, "id", None),
                role,
            )
            raise PermissionDenied("Only drivers can submit EFD receipt proof.")
        try:
            profile = user.driver_profile
        except Driver.DoesNotExist:
            logger.warning(
                "submit_driver_proof denied no_driver_profile request_id=%s user_id=%s",
                fuel_request.pk,
                getattr(user, "id", None),
            )
            raise PermissionDenied("No driver profile for this account.")
        if fuel_request.driver_id != profile.pk:
            logger.warning(
                "submit_driver_proof denied wrong_driver request_id=%s user_id=%s expected_driver_id=%s",
                fuel_request.pk,
                getattr(user, "id", None),
                fuel_request.driver_id,
            )
            raise PermissionDenied("You can only submit proof for your own MVFOs.")
        if fuel_request.mvfo_status != FuelRequest.MvfoStatus.COLLECTED:
            logger.warning(
                "submit_driver_proof denied wrong_status request_id=%s user_id=%s current_status=%s",
                fuel_request.pk,
                getattr(user, "id", None),
                fuel_request.mvfo_status,
            )
            raise ValidationError(
                {
                    "detail": (
                        "EFD receipt can only be submitted when the order is COLLECTED "
                        "(after the station has finished dispensing)."
                    ),
                    "current_mvfo_status": fuel_request.mvfo_status,
                },
            )

        def _pick_file(*names):
            for name in names:
                f = request.FILES.get(name)
                if f is not None:
                    return f
            return None

        efd = (request.data.get("efd_receipt_url") or "").strip()
        odo = (request.data.get("odometer_photo_url") or "").strip()
        driver_pump = (request.data.get("driver_pump_photo_url") or "").strip()
        efd_file = _pick_file("efd_receipt_image", "efd_receipt", "efd_receipt_file", "efd_image")
        odo_file = _pick_file("odometer_photo_image", "odometer_photo", "odometer_file", "odometer_image")
        driver_pump_file = _pick_file(
            "driver_pump_photo_image",
            "driver_pump_photo",
            "driver_pump_file",
            "pump_photo",
        )

        if efd_file:
            logger.info("submit_driver_proof uploading efd request_id=%s", fuel_request.pk)
            _, efd = upload_request_image(
                efd_file,
                reference=fuel_request.reference or f"request-{fuel_request.pk}",
                image_kind="efd_receipt",
            )
        if odo_file:
            logger.info("submit_driver_proof uploading odometer request_id=%s", fuel_request.pk)
            _, odo = upload_request_image(
                odo_file,
                reference=fuel_request.reference or f"request-{fuel_request.pk}",
                image_kind="odometer_photo",
            )
        if driver_pump_file:
            logger.info("submit_driver_proof uploading driver_pump request_id=%s", fuel_request.pk)
            _, driver_pump = upload_request_image(
                driver_pump_file,
                reference=fuel_request.reference or f"request-{fuel_request.pk}",
                image_kind="driver_pump_photo",
            )

        if not efd:
            raise ValidationError(
                {
                    "efd_receipt_url": "EFD receipt URL or image file is required.",
                    "files_received": list(request.FILES.keys()),
                },
            )
        if not odo:
            raise ValidationError(
                {
                    "odometer_photo_url": "Odometer URL or image file is required.",
                    "files_received": list(request.FILES.keys()),
                },
            )
        if (fuel_request.efd_receipt_url or "").strip() and (fuel_request.odometer_photo_url or "").strip():
            raise ValidationError(
                {"detail": "Driver proof has already been submitted for this MVFO."},
            )
        fuel_request.efd_receipt_url = efd
        fuel_request.odometer_photo_url = odo
        if driver_pump:
            fuel_request.driver_pump_photo_url = driver_pump
        fuel_request.mvfo_status = FuelRequest.MvfoStatus.COMPLETED
        fuel_request.status = FuelRequest.LegacyStatus.COMPLETED
        fuel_request.save(
            update_fields=[
                "efd_receipt_url",
                "odometer_photo_url",
                "driver_pump_photo_url",
                "mvfo_status",
                "status",
                "updated_at",
            ],
        )
        logger.info(
            "submit_driver_proof success request_id=%s user_id=%s completed=true has_driver_pump=%s",
            fuel_request.pk,
            getattr(user, "id", None),
            bool(driver_pump),
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


class SystemSettingsViewSet(viewsets.ModelViewSet):
    queryset = SystemSettings.objects.all()
    serializer_class = SystemSettingsSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get_queryset(self):
        settings_obj, _ = SystemSettings.objects.get_or_create(pk=1)
        return SystemSettings.objects.filter(pk=settings_obj.pk).order_by("pk")
