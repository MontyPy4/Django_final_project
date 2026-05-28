from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    LoginView,
    LogoutView,
    RefreshView,
    RegisterView,
    UserAdminViewSet,
)

app_name = 'users'

router = DefaultRouter()
router.register(r'users', UserAdminViewSet, basename='admin-user')

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('token/refresh/', RefreshView.as_view(), name='token-refresh'),
]

urlpatterns += router.urls
