from datetime import date, timedelta
from decimal import Decimal

from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from listings.models import Address, Listing
from users.models import User
from .models import Booking

DUMMY_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}}


@override_settings(CACHES=DUMMY_CACHE)
class BookingBaseTests(APITestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username='bob', email='bob@example.com', password='BobPass123',
            first_name='Bob', last_name='M', role='landlord',
        )
        self.other_landlord = User.objects.create_user(
            username='carl', email='carl@example.com', password='CarlPass123',
            first_name='Carl', last_name='K', role='landlord',
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
        self.other_listing = Listing.objects.create(
            title='House', description='', address=self.addr,
            price=Decimal('1500.00'), rooms=3, housing_type='house',
            owner=self.other_landlord, is_active=True,
        )

    def _login(self, email, password):
        response = self.client.post(
            '/api/auth/login/', {'email': email, 'password': password}, format='json',
        )
        token = response.data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def _payload(self, **overrides):
        data = {
            'listing': self.listing.id,
            'date_from': (date.today() + timedelta(days=30)).isoformat(),
            'date_to': (date.today() + timedelta(days=35)).isoformat(),
        }
        data.update(overrides)
        return data


class BookingCreationTests(BookingBaseTests):
    def test_tenant_can_create_booking(self):
        self._login('alice@example.com', 'AlicePass123')
        response = self.client.post('/api/bookings/', self._payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'pending')
        self.assertEqual(response.data['tenant'], 'alice')

    def test_landlord_cannot_create_booking(self):
        # Bob (landlord) пытается забронировать ЧУЖОЕ объявление,
        # чтобы дойти до role-проверки (а не упасть на 'своё объявление').
        self._login('bob@example.com', 'BobPass123')
        response = self.client.post(
            '/api/bookings/',
            self._payload(listing=self.other_listing.id),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_book_own_listing(self):
        # Если бы кто-то с ролью tenant был владельцем — сериализатор отбил бы 400.
        # Этот тест проверяет именно это правило (отдельно от role-проверки).
        self.tenant.role = 'landlord'  # имитируем что владелец — tenant'ского аккаунта
        self.tenant.save(update_fields=['role'])
        self.listing.owner = self.tenant
        self.listing.save(update_fields=['owner'])
        self.tenant.role = 'tenant'
        self.tenant.save(update_fields=['role'])
        self._login('alice@example.com', 'AlicePass123')
        response = self.client.post('/api/bookings/', self._payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_date_from_cannot_be_in_past(self):
        self._login('alice@example.com', 'AlicePass123')
        response = self.client.post(
            '/api/bookings/',
            self._payload(
                date_from=(date.today() - timedelta(days=5)).isoformat(),
                date_to=(date.today() - timedelta(days=1)).isoformat(),
            ),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_date_to_must_be_after_date_from(self):
        self._login('alice@example.com', 'AlicePass123')
        d = (date.today() + timedelta(days=10)).isoformat()
        response = self.client.post(
            '/api/bookings/',
            self._payload(date_from=d, date_to=d),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_overlap_rejected(self):
        self._login('alice@example.com', 'AlicePass123')
        self.client.post('/api/bookings/', self._payload(), format='json')
        response = self.client.post(
            '/api/bookings/',
            self._payload(
                date_from=(date.today() + timedelta(days=32)).isoformat(),
                date_to=(date.today() + timedelta(days=40)).isoformat(),
            ),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_book_inactive_listing(self):
        self.listing.is_active = False
        self.listing.save(update_fields=['is_active'])
        self._login('alice@example.com', 'AlicePass123')
        response = self.client.post('/api/bookings/', self._payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class BookingCancelTests(BookingBaseTests):
    def _create_booking(self, days_ahead):
        return Booking.objects.create(
            listing=self.listing, tenant=self.tenant,
            date_from=date.today() + timedelta(days=days_ahead),
            date_to=date.today() + timedelta(days=days_ahead + 3),
            status='pending',
        )

    def test_tenant_can_cancel_24h_before(self):
        b = self._create_booking(days_ahead=10)
        self._login('alice@example.com', 'AlicePass123')
        response = self.client.post(f'/api/bookings/{b.id}/cancel/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        b.refresh_from_db()
        self.assertEqual(b.status, 'cancelled')

    def test_cannot_cancel_within_24h(self):
        b = self._create_booking(days_ahead=0)  # начинается сегодня
        self._login('alice@example.com', 'AlicePass123')
        response = self.client.post(f'/api/bookings/{b.id}/cancel/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_landlord_cannot_cancel_tenant_booking(self):
        b = self._create_booking(days_ahead=10)
        self._login('bob@example.com', 'BobPass123')
        response = self.client.post(f'/api/bookings/{b.id}/cancel/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class BookingConfirmRejectTests(BookingBaseTests):
    def _create_booking(self):
        return Booking.objects.create(
            listing=self.listing, tenant=self.tenant,
            date_from=date.today() + timedelta(days=10),
            date_to=date.today() + timedelta(days=15),
            status='pending',
        )

    def test_landlord_can_confirm(self):
        b = self._create_booking()
        self._login('bob@example.com', 'BobPass123')
        response = self.client.post(f'/api/bookings/{b.id}/confirm/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        b.refresh_from_db()
        self.assertEqual(b.status, 'confirmed')

    def test_landlord_can_reject(self):
        b = self._create_booking()
        self._login('bob@example.com', 'BobPass123')
        response = self.client.post(f'/api/bookings/{b.id}/reject/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        b.refresh_from_db()
        self.assertEqual(b.status, 'cancelled')

    def test_tenant_cannot_confirm(self):
        b = self._create_booking()
        self._login('alice@example.com', 'AlicePass123')
        response = self.client.post(f'/api/bookings/{b.id}/confirm/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
