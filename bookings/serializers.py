from datetime import date

from rest_framework import serializers

from .models import Booking


class BookingSerializer(serializers.ModelSerializer):
    tenant = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Booking
        fields = ('id', 'listing', 'tenant', 'date_from', 'date_to', 'status', 'created_at')
        read_only_fields = ('id', 'tenant', 'status', 'created_at')

    def validate_date_from(self, value):
        if value < date.today():
            raise serializers.ValidationError('Дата заезда не может быть в прошлом.')
        return value

    def validate(self, attrs):
        listing = attrs.get('listing') or getattr(self.instance, 'listing', None)
        date_from = attrs.get('date_from') or getattr(self.instance, 'date_from', None)
        date_to = attrs.get('date_to') or getattr(self.instance, 'date_to', None)

        if listing and not listing.is_active:
            raise serializers.ValidationError(
                {'listing': 'Нельзя забронировать неактивное объявление.'}
            )

        if date_from and date_to and date_to <= date_from:
            raise serializers.ValidationError(
                {'date_to': 'Дата выезда должна быть позже даты заезда.'}
            )

        request = self.context.get('request')
        if request and listing and listing.owner_id == request.user.id:
            raise serializers.ValidationError(
                'Нельзя бронировать собственное объявление.'
            )

        if listing and date_from and date_to:
            overlapping = Booking.objects.filter(
                listing=listing,
                status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED],
                date_from__lte=date_to,
                date_to__gte=date_from,
            )
            if self.instance:
                overlapping = overlapping.exclude(pk=self.instance.pk)
            if overlapping.exists():
                raise serializers.ValidationError(
                    'На выбранные даты уже есть бронирование.'
                )

        return attrs
