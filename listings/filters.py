from django_filters import rest_framework as filters

from .models import Listing


class ListingFilter(filters.FilterSet):
    price_min = filters.NumberFilter(field_name='price', lookup_expr='gte')
    price_max = filters.NumberFilter(field_name='price', lookup_expr='lte')
    region = filters.CharFilter(field_name='address__region', lookup_expr='icontains')
    city = filters.CharFilter(field_name='address__city', lookup_expr='icontains')
    district = filters.CharFilter(field_name='address__district', lookup_expr='icontains')
    rooms_min = filters.NumberFilter(field_name='rooms', lookup_expr='gte')
    rooms_max = filters.NumberFilter(field_name='rooms', lookup_expr='lte')
    housing_type = filters.ChoiceFilter(choices=Listing.HousingType.choices)
    is_active = filters.BooleanFilter()

    class Meta:
        model = Listing
        fields = [
            'price_min',
            'price_max',
            'region',
            'city',
            'district',
            'rooms_min',
            'rooms_max',
            'housing_type',
            'is_active',
        ]
