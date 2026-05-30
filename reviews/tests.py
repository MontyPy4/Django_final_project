from datetime import date, timedelta
from decimal import Decimal

from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from bookings.models import Booking
from listings.models import Address, Listing
from users.models import User
from .models import Review

DUMMY_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}}


@override_settings(CACHES=DUMMY_CACHE)
class ReviewTests(APITestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username='bob', email='bob@example.com', password='BobPass123',
            first_name='Bob', last_name='M', role='landlord',
        )
        self.tenant = User.objects.create_user(
            username='alice', email='alice@example.com', password='AlicePass123',
            first_name='Alice', last_name='S', role='tenant',
        )
        self.addr, _ = Address.objects.get_or_create(
            region='LS', city='Hannover', district='Mitte',
        )
        self.listing = Listing.objects.create(
            title='Studio', description='', address=self.addr,
            price=Decimal('850.00'), rooms=1, housing_type='studio',
            owner=self.landlord, is_active=True,
        )

    def _login(self, email, password):
        response = self.client.post(
            '/api/auth/login/', {'email': email, 'password': password}, format='json',
        )
        token = response.data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def _create_completed_stay(self):
        return Booking.objects.create(
            listing=self.listing, tenant=self.tenant,
            date_from=date.today() - timedelta(days=10),
            date_to=date.today() - timedelta(days=3),
            status='confirmed',
        )

    def test_review_requires_completed_stay(self):
        self._login('alice@example.com', 'AlicePass123')
        response = self.client.post(
            '/api/reviews/',
            {'listing': self.listing.id, 'rating': 5, 'text': 'Great!'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    def test_review_success_after_completed_stay(self):
        self._create_completed_stay()
        self._login('alice@example.com', 'AlicePass123')
        response = self.client.post(
            '/api/reviews/',
            {'listing': self.listing.id, 'rating': 5, 'text': 'Great stay!'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Review.objects.filter(
            author=self.tenant, listing=self.listing).exists())

    def test_review_for_future_booking_rejected(self):
        # бронь подтверждена, но дата выезда ещё не наступила
        Booking.objects.create(
            listing=self.listing, tenant=self.tenant,
            date_from=date.today() + timedelta(days=5),
            date_to=date.today() + timedelta(days=10),
            status='confirmed',
        )
        self._login('alice@example.com', 'AlicePass123')
        response = self.client.post(
            '/api/reviews/',
            {'listing': self.listing.id, 'rating': 5, 'text': 'Cant wait!'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_review_rejected(self):
        self._create_completed_stay()
        self._login('alice@example.com', 'AlicePass123')
        first = self.client.post(
            '/api/reviews/',
            {'listing': self.listing.id, 'rating': 5, 'text': 'First'},
            format='json',
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        second = self.client.post(
            '/api/reviews/',
            {'listing': self.listing.id, 'rating': 4, 'text': 'Second try'},
            format='json',
        )
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)

    def test_landlord_cannot_leave_review(self):
        self._login('bob@example.com', 'BobPass123')
        response = self.client.post(
            '/api/reviews/',
            {'listing': self.listing.id, 'rating': 5, 'text': 'My own place'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_rating_out_of_range_rejected(self):
        self._create_completed_stay()
        self._login('alice@example.com', 'AlicePass123')
        response = self.client.post(
            '/api/reviews/',
            {'listing': self.listing.id, 'rating': 6, 'text': 'Too high'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('rating', response.data)

    def test_rating_zero_rejected(self):
        self._create_completed_stay()
        self._login('alice@example.com', 'AlicePass123')
        response = self.client.post(
            '/api/reviews/',
            {'listing': self.listing.id, 'rating': 0, 'text': 'Too low'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
