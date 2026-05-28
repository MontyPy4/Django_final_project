from rest_framework.routers import DefaultRouter

from .views import ReviewViewSet

app_name = 'reviews'

router = DefaultRouter()
router.register(r'', ReviewViewSet, basename='review')

urlpatterns = router.urls
