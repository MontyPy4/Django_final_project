from decimal import Decimal

from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from users.models import User
from .models import Address, Listing

DUMMY_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}}


@override_settings(CACHES=DUMMY_CACHE)
class ListingBaseTests(APITestCase):
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

    def _login(self, email, password):
        response = self.client.post(
            '/api/auth/login/',
            {'email': email, 'password': password},
            format='json',
        )
        token = response.data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def _logout(self):
        self.client.credentials()

    def _make_listing(self, **kwargs):
        addr, _ = Address.objects.get_or_create(
            region='Lower Saxony', city='Hannover', district='Mitte',
        )
        defaults = dict(
            title='Studio', description='Nice studio', address=addr,
            price=Decimal('850.00'), rooms=1, housing_type='studio',
            owner=self.landlord, is_active=True,
        )
        defaults.update(kwargs)
        return Listing.objects.create(**defaults)

    def _payload(self, **overrides):
        data = {
            'title': 'Cozy studio',
            'description': 'Near central station',
            'address': {'region': 'Lower Saxony', 'city': 'Hannover', 'district': 'Mitte'},
            'price': '850.00',
            'rooms': 1,
            'housing_type': 'studio',
        }
        data.update(overrides)
        return data


class ListingCRUDTests(ListingBaseTests):
    def test_landlord_can_create(self):
        self._login('bob@example.com', 'BobPass123')
        response = self.client.post('/api/listings/', self._payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['owner'], 'bob')
        self.assertEqual(response.data['is_active'], True)

    def test_tenant_cannot_create(self):
        self._login('alice@example.com', 'AlicePass123')
        response = self.client.post('/api/listings/', self._payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_can_list(self):
        self._make_listing()
        response = self.client.get('/api/listings/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    def test_anonymous_can_retrieve(self):
        listing = self._make_listing()
        response = self.client.get(f'/api/listings/{listing.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_owner_can_update(self):
        listing = self._make_listing()
        self._login('bob@example.com', 'BobPass123')
        response = self.client.patch(
            f'/api/listings/{listing.id}/', {'price': '999.00'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        listing.refresh_from_db()
        self.assertEqual(listing.price, Decimal('999.00'))

    def test_other_landlord_cannot_update(self):
        listing = self._make_listing()
        self._login('carl@example.com', 'CarlPass123')
        response = self.client.patch(
            f'/api/listings/{listing.id}/', {'price': '1.00'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_can_delete(self):
        listing = self._make_listing()
        self._login('bob@example.com', 'BobPass123')
        response = self.client.delete(f'/api/listings/{listing.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_other_landlord_cannot_delete(self):
        listing = self._make_listing()
        self._login('carl@example.com', 'CarlPass123')
        response = self.client.delete(f'/api/listings/{listing.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_can_toggle_status(self):
        listing = self._make_listing()
        self._login('bob@example.com', 'BobPass123')
        response = self.client.patch(f'/api/listings/{listing.id}/toggle_status/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        listing.refresh_from_db()
        self.assertFalse(listing.is_active)


class ListingValidationTests(ListingBaseTests):
    def test_price_must_be_positive(self):
        self._login('bob@example.com', 'BobPass123')
        response = self.client.post(
            '/api/listings/', self._payload(price='-5.00'), format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('price', response.data)

    def test_rooms_must_be_positive(self):
        self._login('bob@example.com', 'BobPass123')
        response = self.client.post(
            '/api/listings/', self._payload(rooms=0), format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('rooms', response.data)

    def test_title_not_empty(self):
        self._login('bob@example.com', 'BobPass123')
        response = self.client.post(
            '/api/listings/', self._payload(title=''), format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_address_is_reused_via_get_or_create(self):
        self._login('bob@example.com', 'BobPass123')
        r1 = self.client.post('/api/listings/', self._payload(), format='json')
        r2 = self.client.post(
            '/api/listings/', self._payload(title='Second'), format='json',
        )
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        self.assertEqual(r1.data['address']['id'], r2.data['address']['id'])


class ListingFilterTests(ListingBaseTests):
    def setUp(self):
        super().setUp()
        a1, _ = Address.objects.get_or_create(region='LS', city='Hannover', district='Mitte')
        a2, _ = Address.objects.get_or_create(region='LS', city='Bremen', district='')
        Listing.objects.create(
            title='Hannover house', description='', address=a1,
            price=2000, rooms=5, housing_type='house', owner=self.landlord,
        )
        Listing.objects.create(
            title='Bremen studio', description='', address=a2,
            price=500, rooms=1, housing_type='studio', owner=self.landlord,
        )

    def test_filter_by_city(self):
        response = self.client.get('/api/listings/?city=Hannover')
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['address']['city'], 'Hannover')

    def test_filter_by_price_range(self):
        response = self.client.get('/api/listings/?price_max=1000')
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['title'], 'Bremen studio')

    def test_filter_by_housing_type(self):
        response = self.client.get('/api/listings/?housing_type=house')
        self.assertEqual(response.data['count'], 1)

    def test_search_in_title(self):
        response = self.client.get('/api/listings/?search=Hannover')
        self.assertEqual(response.data['count'], 1)

    def test_ordering_by_price(self):
        response = self.client.get('/api/listings/?ordering=price')
        prices = [Decimal(item['price']) for item in response.data['results']]
        self.assertEqual(prices, sorted(prices))
