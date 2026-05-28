from datetime import date, timedelta

from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Booking
from .serializers import BookingSerializer


class BookingViewSet(viewsets.ModelViewSet):
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return (
            Booking.objects
            .filter(Q(tenant=user) | Q(listing__owner=user))
            .select_related('listing', 'tenant')
        )

    def perform_create(self, serializer):
        if getattr(self.request.user, 'role', None) != 'tenant':
            raise PermissionDenied('Бронировать могут только арендаторы.')
        serializer.save(tenant=self.request.user)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        booking = self.get_object()
        if booking.tenant_id != request.user.id:
            return Response(
                {'error': 'Отменить бронь может только её владелец.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if booking.status != Booking.Status.PENDING:
            return Response(
                {'error': 'Отменить можно только бронь в статусе pending.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if date.today() > booking.date_from - timedelta(days=1):
            return Response(
                {'error': 'Отменить бронь можно не позднее чем за 24 часа до даты заселения.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        booking.status = Booking.Status.CANCELLED
        booking.save(update_fields=['status'])
        return Response(BookingSerializer(booking).data)

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        booking = self.get_object()
        if booking.listing.owner_id != request.user.id:
            return Response(
                {'error': 'Подтвердить бронь может только владелец объявления.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if booking.status == Booking.Status.CANCELLED:
            return Response(
                {'error': 'Нельзя подтвердить отменённую бронь.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        booking.status = Booking.Status.CONFIRMED
        booking.save(update_fields=['status'])
        return Response(BookingSerializer(booking).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        booking = self.get_object()
        if booking.listing.owner_id != request.user.id:
            return Response(
                {'error': 'Отклонить бронь может только владелец объявления.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if booking.status == Booking.Status.CANCELLED:
            return Response(
                {'error': 'Бронь уже отменена.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        booking.status = Booking.Status.CANCELLED
        booking.save(update_fields=['status'])
        return Response(BookingSerializer(booking).data)

    @action(detail=False, methods=['get'])
    def active(self, request):
        qs = self.get_queryset().filter(
            status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED]
        )
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(BookingSerializer(page, many=True).data)
        return Response(BookingSerializer(qs, many=True).data)

    @action(detail=False, methods=['get'])
    def history(self, request):
        today = date.today()
        qs = self.get_queryset().filter(
            Q(status=Booking.Status.CANCELLED) | Q(date_to__lt=today)
        )
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(BookingSerializer(page, many=True).data)
        return Response(BookingSerializer(qs, many=True).data)
