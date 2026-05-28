from django.db.models import Avg
from rest_framework import serializers

from reviews.models import Review

from .models import Address, Listing


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = ('id', 'region', 'city', 'district')
        read_only_fields = ('id',)
        extra_kwargs = {
            'region': {'required': True, 'allow_blank': False},
            'city': {'required': True, 'allow_blank': False},
            'district': {'required': False, 'allow_blank': True, 'default': ''},
        }
        validators = []


class ListingSerializer(serializers.ModelSerializer):
    owner = serializers.StringRelatedField(read_only=True)
    address = AddressSerializer()
    average_rating = serializers.SerializerMethodField()
    reviews_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Listing
        fields = (
            'id',
            'title',
            'description',
            'address',
            'price',
            'rooms',
            'housing_type',
            'is_active',
            'owner',
            'views_count',
            'reviews_count',
            'average_rating',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id',
            'owner',
            'views_count',
            'reviews_count',
            'average_rating',
            'created_at',
            'updated_at',
        )

    def get_average_rating(self, obj):
        return Review.objects.filter(listing=obj).aggregate(Avg('rating'))['rating__avg']

    def validate_title(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError('Заголовок не может быть пустым.')
        return value

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError('Цена должна быть больше 0.')
        return value

    def validate_rooms(self, value):
        if value <= 0:
            raise serializers.ValidationError('Количество комнат должно быть больше 0.')
        return value

    @staticmethod
    def _resolve_address(address_data):
        address, _ = Address.objects.get_or_create(
            region=address_data['region'].strip(),
            city=address_data['city'].strip(),
            district=address_data.get('district', '').strip(),
        )
        return address

    def create(self, validated_data):
        address_data = validated_data.pop('address')
        validated_data['address'] = self._resolve_address(address_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        address_data = validated_data.pop('address', None)
        if address_data is not None:
            instance.address = self._resolve_address(address_data)
        return super().update(instance, validated_data)


class ListingShortSerializer(serializers.ModelSerializer):
    address = AddressSerializer(read_only=True)
    reviews_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Listing
        fields = (
            'id',
            'title',
            'address',
            'price',
            'rooms',
            'housing_type',
            'is_active',
            'views_count',
            'reviews_count',
            'created_at',
        )
