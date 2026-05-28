import hashlib
from datetime import timedelta

from django.db.models import Count, F
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .filters import ListingFilter
from .models import Listing, SearchHistory, ViewHistory
from .permissions import IsOwnerOrReadOnly
from .serializers import ListingSerializer, ListingShortSerializer

VIEW_COOLDOWN_HOURS = 24


def _visitor_fingerprint(request):
    ip = (
        request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
        or request.META.get('REMOTE_ADDR', '')
    )
    ua = request.META.get('HTTP_USER_AGENT', '')
    raw = f'{ip}|{ua}'
    return hashlib.sha256(raw.encode('utf-8', errors='replace')).hexdigest()


class ListingViewSet(viewsets.ModelViewSet):
    serializer_class = ListingSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrReadOnly]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ListingFilter
    search_fields = ['title', 'description']
    ordering_fields = ['price', 'created_at', 'views_count', 'reviews_count', 'rooms']
    ordering = ['-created_at']

    def get_permissions(self):
        if self.action in ('list', 'retrieve', 'popular_searches'):
            return [AllowAny()]
        if self.action == 'my_listings':
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsOwnerOrReadOnly()]

    def get_queryset(self):
        base = Listing.objects.annotate(reviews_count=Count('reviews', distinct=True))
        if self.action in ('list', 'retrieve'):
            return base.filter(is_active=True)
        return base

    def get_serializer_class(self):
        if self.action == 'list':
            return ListingShortSerializer
        return ListingSerializer

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def list(self, request, *args, **kwargs):
        search_query = request.query_params.get('search', '').strip()
        if search_query and request.user.is_authenticated:
            SearchHistory.objects.create(user=request.user, keyword=search_query)
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()

        user = request.user if request.user.is_authenticated else None
        is_owner = bool(user and instance.owner_id == user.id)
        visitor_key = _visitor_fingerprint(request)

        cooldown_start = timezone.now() - timedelta(hours=VIEW_COOLDOWN_HOURS)
        recently_viewed = ViewHistory.objects.filter(
            listing=instance,
            visitor_key=visitor_key,
            viewed_at__gte=cooldown_start,
        ).exists()

        if not is_owner and not recently_viewed:
            Listing.objects.filter(pk=instance.pk).update(views_count=F('views_count') + 1)
            instance.refresh_from_db(fields=['views_count'])
            ViewHistory.objects.create(
                user=user,
                listing=instance,
                visitor_key=visitor_key,
            )

        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=True, methods=['patch'], url_path='toggle_status')
    def toggle_status(self, request, pk=None):
        listing = self.get_object()
        listing.is_active = not listing.is_active
        listing.save(update_fields=['is_active', 'updated_at'])
        return Response(
            {'id': listing.id, 'is_active': listing.is_active},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['get'], url_path='my_listings')
    def my_listings(self, request):
        queryset = Listing.objects.filter(owner=request.user)
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = ListingShortSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = ListingShortSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='popular_searches')
    def popular_searches(self, request):
        top = (
            SearchHistory.objects
            .values('keyword')
            .annotate(count=Count('keyword'))
            .order_by('-count')[:10]
        )
        return Response(list(top))
