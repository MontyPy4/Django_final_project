from django.contrib import admin

from .models import Address, Listing


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ('id', 'region', 'city', 'district')
    list_filter = ('region', 'city')
    search_fields = ('region', 'city', 'district')


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'address', 'price', 'rooms', 'housing_type', 'is_active', 'owner', 'views_count')
    list_filter = ('housing_type', 'is_active', 'address__region', 'address__city')
    search_fields = ('title', 'description')
    raw_id_fields = ('owner', 'address')
    readonly_fields = ('views_count', 'created_at', 'updated_at')
