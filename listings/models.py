from django.conf import settings
from django.db import models


class Address(models.Model):
    region = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    district = models.CharField(max_length=100, blank=True, default='')

    class Meta:
        ordering = ['region', 'city', 'district']
        constraints = [
            models.UniqueConstraint(
                fields=['region', 'city', 'district'],
                name='unique_address_region_city_district',
            ),
        ]

    def __str__(self):
        if self.district:
            return f'{self.region}, {self.city}, {self.district}'
        return f'{self.region}, {self.city}'


class Listing(models.Model):
    class HousingType(models.TextChoices):
        APARTMENT = 'apartment', 'Apartment'
        HOUSE = 'house', 'House'
        STUDIO = 'studio', 'Studio'
        ROOM = 'room', 'Room'

    title = models.CharField(max_length=200)
    description = models.TextField()
    address = models.ForeignKey(
        Address,
        on_delete=models.PROTECT,
        related_name='listings',
        null=True,
        blank=True,
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    rooms = models.PositiveIntegerField()
    housing_type = models.CharField(max_length=20, choices=HousingType.choices)
    is_active = models.BooleanField(default=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='listings',
    )
    views_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class SearchHistory(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='search_history',
    )
    keyword = models.CharField(max_length=200)
    searched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-searched_at']

    def __str__(self):
        return f'{self.user} -> {self.keyword}'


class ViewHistory(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='view_history',
        null=True,
        blank=True,
    )
    listing = models.ForeignKey(
        Listing,
        on_delete=models.CASCADE,
        related_name='view_history',
    )
    visitor_key = models.CharField(max_length=64, db_index=True, default='')
    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-viewed_at']
        indexes = [
            models.Index(fields=['listing', 'visitor_key', 'viewed_at']),
        ]

    def __str__(self):
        return f'{self.user or "anon"} -> {self.listing}'
