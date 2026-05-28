from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        TENANT = 'tenant', 'Tenant'
        LANDLORD = 'landlord', 'Landlord'

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.TENANT)
    phone = models.CharField(max_length=20, blank=True)

    REQUIRED_FIELDS = ['email']

    @property
    def is_tenant(self) -> bool:
        return self.role == self.Role.TENANT

    @property
    def is_landlord(self) -> bool:
        return self.role == self.Role.LANDLORD

    def __str__(self):
        return self.username
