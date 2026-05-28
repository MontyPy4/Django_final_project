from rest_framework_simplejwt.authentication import JWTAuthentication

ACCESS_COOKIE_NAME = 'access_token'
REFRESH_COOKIE_NAME = 'refresh_token'


class CookieJWTAuthentication(JWTAuthentication):
    """JWT authentication that also reads access token from an httpOnly cookie.

    Order of precedence: Authorization header first (for Swagger / Postman /
    mobile clients), then `access_token` cookie (for browser apps).
    """

    def authenticate(self, request):
        header = self.get_header(request)
        if header is not None:
            return super().authenticate(request)

        raw_token = request.COOKIES.get(ACCESS_COOKIE_NAME)
        if raw_token is None:
            return None

        validated_token = self.get_validated_token(raw_token)
        return self.get_user(validated_token), validated_token
