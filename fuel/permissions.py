from rest_framework import permissions

from users.models import User


class IsAdminRole(permissions.BasePermission):
    """Only users with role ADMIN (or Django superuser) may perform the action."""

    message = "Only administrators can manage fuel stations."

    def has_permission(self, request, view):
        u = request.user
        if not u or not u.is_authenticated:
            return False
        if getattr(u, "is_superuser", False):
            return True
        return getattr(u, "role", None) == User.Role.ADMIN
