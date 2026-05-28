import logging

from django.conf import settings
from django.contrib.auth import authenticate
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import CreateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .authentication import ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME
from .models import User
from .permissions import IsAdmin
from .serializers import (
    AdminUserSerializer,
    LoginSerializer,
    RegisterSerializer,
    UserSerializer,
)
from .throttles import LoginRateThrottle

logger = logging.getLogger(__name__)

REFRESH_COOKIE_PATH = '/api/auth/'


def _set_access_cookie(response, access_token):
    response.set_cookie(
        ACCESS_COOKIE_NAME,
        access_token,
        max_age=int(settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds()),
        httponly=True,
        secure=not settings.DEBUG,
        samesite='Lax',
    )


def _set_refresh_cookie(response, refresh_token):
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        refresh_token,
        max_age=int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds()),
        httponly=True,
        secure=not settings.DEBUG,
        samesite='Lax',
        path=REFRESH_COOKIE_PATH,
    )


def _clear_jwt_cookies(response):
    response.delete_cookie(ACCESS_COOKIE_NAME)
    response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)


class RegisterView(CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]
    throttle_scope = 'login'

    INVALID_CREDENTIALS = {'error': 'Неверные учётные данные'}

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']
        password = serializer.validated_data['password']

        existing = User.objects.filter(email__iexact=email).first()
        if existing is None:
            logger.info('Login failed for unknown email %r', email)
            return Response(self.INVALID_CREDENTIALS, status=status.HTTP_401_UNAUTHORIZED)

        user = authenticate(request, username=existing.username, password=password)
        if user is None:
            if not existing.is_active:
                logger.warning('Login attempt on inactive account email=%r', email)
            else:
                logger.info('Login failed: bad password for email=%r', email)
            return Response(self.INVALID_CREDENTIALS, status=status.HTTP_401_UNAUTHORIZED)

        if not user.is_active:
            logger.warning('Login attempt on inactive account email=%r', email)
            return Response(self.INVALID_CREDENTIALS, status=status.HTTP_401_UNAUTHORIZED)

        refresh = RefreshToken.for_user(user)
        access_str = str(refresh.access_token)
        refresh_str = str(refresh)
        response = Response(
            {
                'access': access_str,
                'refresh': refresh_str,
                'user': UserSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )
        _set_access_cookie(response, access_str)
        _set_refresh_cookie(response, refresh_str)
        return response


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh = request.data.get('refresh') or request.COOKIES.get(REFRESH_COOKIE_NAME)
        if refresh:
            try:
                RefreshToken(refresh).blacklist()
            except TokenError:
                logger.info('Logout with invalid/expired refresh token for user_id=%s', request.user.id)

        response = Response({'message': 'Выход выполнен'}, status=status.HTTP_200_OK)
        _clear_jwt_cookies(response)
        return response


class RefreshView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_str = request.data.get('refresh') or request.COOKIES.get(REFRESH_COOKIE_NAME)
        if not refresh_str:
            return Response(
                {'detail': 'No refresh token provided.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            refresh = RefreshToken(refresh_str)
        except TokenError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_401_UNAUTHORIZED)

        new_access = str(refresh.access_token)
        body = {'access': new_access}
        new_refresh_str = None

        if settings.SIMPLE_JWT.get('ROTATE_REFRESH_TOKENS', False):
            if settings.SIMPLE_JWT.get('BLACKLIST_AFTER_ROTATION', False):
                try:
                    refresh.blacklist()
                except AttributeError:
                    pass
            refresh.set_jti()
            refresh.set_exp()
            refresh.set_iat()
            new_refresh_str = str(refresh)
            body['refresh'] = new_refresh_str

        response = Response(body, status=status.HTTP_200_OK)
        _set_access_cookie(response, new_access)
        if new_refresh_str:
            _set_refresh_cookie(response, new_refresh_str)
        return response


class UserAdminViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = User.objects.all().order_by('id')
    serializer_class = AdminUserSerializer
    permission_classes = [IsAuthenticated, IsAdmin]

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        target = self.get_object()
        if not target.is_active:
            target.is_active = True
            target.save(update_fields=['is_active'])
            logger.info('Admin %s activated user_id=%s', request.user.id, target.id)
        return Response(AdminUserSerializer(target).data)

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        target = self.get_object()
        if target.id == request.user.id:
            return Response(
                {'error': 'Нельзя деактивировать самого себя.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if target.is_active:
            target.is_active = False
            target.save(update_fields=['is_active'])
            logger.warning('Admin %s deactivated user_id=%s', request.user.id, target.id)
        return Response(AdminUserSerializer(target).data)

    @action(detail=True, methods=['post'])
    def promote(self, request, pk=None):
        target = self.get_object()
        if not target.is_staff:
            target.is_staff = True
            target.save(update_fields=['is_staff'])
            logger.warning('Admin %s promoted user_id=%s to staff', request.user.id, target.id)
        return Response(AdminUserSerializer(target).data)
