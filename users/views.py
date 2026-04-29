from typing import Optional

from django.contrib.auth import authenticate
from rest_framework import mixins, status, viewsets
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from fuel.models import Driver
from fuel.permissions import IsAdminRole
from fuel.serializers import VehicleSerializer

from .models import User
from .serializers import UserCreateSerializer, UserSerializer, UserUpdateSerializer


def _auth_session_payload(user: User, *, include_token: Optional[str] = None) -> dict:
    """Shared shape for login and GET /auth/me/ (mobile app uses vehicles for MVFO)."""
    user = User.objects.select_related("assigned_station").get(pk=user.pk)
    driver_id = None
    vehicles: list = []
    if user.role == User.Role.DRIVER:
        try:
            d = Driver.objects.prefetch_related("vehicles").get(user_id=user.pk)
            driver_id = d.pk
            qs = d.vehicles.filter(is_active=True).order_by("-registered_at")
            vehicles = VehicleSerializer(qs, many=True).data
        except Driver.DoesNotExist:
            pass
    assigned_station = None
    if user.assigned_station_id:
        s = user.assigned_station
        assigned_station = {"id": s.pk, "name": s.name, "region": s.region}
    payload = {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "driver_id": driver_id,
        "region": user.region or "",
        "assigned_station": assigned_station,
        "vehicles": vehicles,
    }
    if include_token is not None:
        payload["token"] = include_token
    return payload


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def login(request):
    phone = (request.data.get("phone") or "").strip()
    email = (request.data.get("email") or "").strip().lower()
    password = request.data.get("password")
    if (not phone and not email) or not password:
        return Response({"detail": "phone and password are required"}, status=400)

    user = None
    if phone:
        try:
            login_user = User.objects.get(phone=phone)
            user = authenticate(request, username=login_user.email, password=password)
        except User.DoesNotExist:
            user = None
    elif email:
        # Backward-compatible fallback while clients migrate to phone login.
        user = authenticate(request, username=email, password=password)

    if user is None or not user.is_active:
        return Response({"detail": "Invalid credentials"}, status=401)
    user = User.objects.select_related("assigned_station").get(pk=user.pk)
    token, _ = Token.objects.get_or_create(user=user)
    payload = _auth_session_payload(user, include_token=token.key)
    return Response(payload)


@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def me(request):
    """Current user + assigned vehicles (drivers) for the mobile app."""
    return Response(_auth_session_payload(request.user))


class UserViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = User.objects.select_related("assigned_station").order_by("-date_joined")
    serializer_class = UserSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        if self.action in ("update", "partial_update"):
            return UserUpdateSerializer
        return UserSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        user = serializer.instance
        read = UserSerializer(user, context={"request": request})
        headers = self.get_success_headers(read.data)
        return Response(read.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_destroy(self, instance: User):
        if instance.is_superuser:
            raise PermissionDenied("Cannot delete a superuser account.")
        if instance.pk == self.request.user.pk:
            raise PermissionDenied("Cannot delete your own account.")
        instance.delete()
