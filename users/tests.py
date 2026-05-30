from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import User

DUMMY_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}}


@override_settings(CACHES=DUMMY_CACHE)
class RegisterTests(APITestCase):
    url = reverse('users:register')

    def _payload(self, **overrides):
        data = {
            'username': 'alice',
            'first_name': 'Alice',
            'last_name': 'Smith',
            'email': 'alice@example.com',
            'password': 'StrongPass123',
            'password_confirm': 'StrongPass123',
            'role': 'tenant',
        }
        data.update(overrides)
        return data

    def test_register_success(self):
        response = self.client.post(self.url, self._payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email='alice@example.com').exists())

    def test_register_requires_first_and_last_name(self):
        response = self.client.post(
            self.url, self._payload(first_name='', last_name=''), format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('first_name', response.data)
        self.assertIn('last_name', response.data)

    def test_register_rejects_common_password(self):
        response = self.client.post(
            self.url,
            self._payload(password='password', password_confirm='password'),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)

    def test_register_rejects_numeric_password(self):
        response = self.client.post(
            self.url,
            self._payload(password='12345678', password_confirm='12345678'),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_password_mismatch(self):
        response = self.client.post(
            self.url,
            self._payload(password='StrongPass123', password_confirm='Different123'),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_duplicate_email(self):
        self.client.post(self.url, self._payload(), format='json')
        response = self.client.post(
            self.url, self._payload(username='alice2'), format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)

    def test_password_is_hashed(self):
        self.client.post(self.url, self._payload(), format='json')
        user = User.objects.get(email='alice@example.com')
        self.assertNotEqual(user.password, 'StrongPass123')
        self.assertTrue(user.check_password('StrongPass123'))


@override_settings(CACHES=DUMMY_CACHE)
class LoginTests(APITestCase):
    url = reverse('users:login')

    def setUp(self):
        self.user = User.objects.create_user(
            username='alice', email='alice@example.com', password='StrongPass123',
            first_name='Alice', last_name='Smith', role='tenant',
        )

    def test_login_by_email_success(self):
        response = self.client.post(
            self.url,
            {'email': 'alice@example.com', 'password': 'StrongPass123'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertIn('access_token', response.cookies)
        self.assertIn('refresh_token', response.cookies)

    def test_login_wrong_password_returns_generic_401(self):
        response = self.client.post(
            self.url,
            {'email': 'alice@example.com', 'password': 'wrong'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data, {'error': 'Неверные учётные данные'})

    def test_login_unknown_email_returns_same_message(self):
        response = self.client.post(
            self.url,
            {'email': 'nobody@example.com', 'password': 'any'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data, {'error': 'Неверные учётные данные'})

    def test_login_inactive_user_returns_same_message(self):
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        response = self.client.post(
            self.url,
            {'email': 'alice@example.com', 'password': 'StrongPass123'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data, {'error': 'Неверные учётные данные'})


@override_settings(CACHES=DUMMY_CACHE)
class AdminEndpointsTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@example.com', password='AdminPass123',
            first_name='Admin', last_name='Root',
        )
        self.regular = User.objects.create_user(
            username='bob', email='bob@example.com', password='BobPass123',
            first_name='Bob', last_name='Mueller', role='landlord',
        )

    def _login_as(self, email, password):
        response = self.client.post(
            reverse('users:login'),
            {'email': email, 'password': password},
            format='json',
        )
        token = response.data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_list_users_requires_admin(self):
        self._login_as('bob@example.com', 'BobPass123')
        response = self.client.get('/api/auth/users/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_list_users(self):
        self._login_as('admin@example.com', 'AdminPass123')
        response = self.client.get('/api/auth/users/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_admin_can_deactivate_user(self):
        self._login_as('admin@example.com', 'AdminPass123')
        response = self.client.post(f'/api/auth/users/{self.regular.id}/deactivate/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.regular.refresh_from_db()
        self.assertFalse(self.regular.is_active)

    def test_admin_cannot_deactivate_self(self):
        self._login_as('admin@example.com', 'AdminPass123')
        response = self.client.post(f'/api/auth/users/{self.admin.id}/deactivate/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_can_promote_user(self):
        self._login_as('admin@example.com', 'AdminPass123')
        response = self.client.post(f'/api/auth/users/{self.regular.id}/promote/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.regular.refresh_from_db()
        self.assertTrue(self.regular.is_staff)
