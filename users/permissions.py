from rest_framework.permissions import BasePermission


class IsLandlord(BasePermission):
    message = 'Доступ только для арендодателей.'

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == 'landlord'
        )


class IsTenant(BasePermission):
    message = 'Доступ только для арендаторов.'

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == 'tenant'
        )


class IsAdmin(BasePermission):
    message = 'Доступ только для администратора.'

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_staff or request.user.is_superuser)
        )
