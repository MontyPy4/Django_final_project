from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from bookings.models import Booking

from .models import Review
from .serializers import ReviewSerializer


class ReviewViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Review.objects.select_related('listing', 'author').all()
    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['listing']

    def create(self, request, *args, **kwargs):
        if getattr(request.user, 'role', None) != 'tenant':
            return Response(
                {'error': 'Отзывы могут оставлять только арендаторы.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        listing = serializer.validated_data['listing']

        has_completed_stay = Booking.objects.filter(
            tenant=request.user,
            listing=listing,
            status=Booking.Status.CONFIRMED,
            date_to__lt=timezone.now().date(),
        ).exists()
        if not has_completed_stay:
            return Response(
                {'error': 'Отзыв можно оставить только после фактически завершённого проживания.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if Review.objects.filter(listing=listing, author=request.user).exists():
            return Response(
                {'error': 'Вы уже оставили отзыв на это объявление.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    @action(detail=False, methods=['get'], url_path='listing_reviews')
    def listing_reviews(self, request):
        listing_id = request.query_params.get('listing')
        qs = self.get_queryset()
        if listing_id:
            qs = qs.filter(listing_id=listing_id)
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(ReviewSerializer(page, many=True).data)
        return Response(ReviewSerializer(qs, many=True).data)
