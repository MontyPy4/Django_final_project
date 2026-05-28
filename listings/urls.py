from rest_framework.routers import DefaultRouter

from .views import ListingViewSet

app_name = 'listings'

router = DefaultRouter()
router.register(r'', ListingViewSet, basename='listing')

urlpatterns = router.urls
