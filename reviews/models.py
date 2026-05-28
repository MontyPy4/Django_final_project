from django.conf import settings
from django.db import models


class Review(models.Model):
    RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]

    listing = models.ForeignKey(
        'listings.Listing',
        on_delete=models.CASCADE,
        related_name='reviews',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reviews',
    )
    rating = models.PositiveIntegerField(choices=RATING_CHOICES)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['listing', 'author']
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.author} -> {self.listing} ({self.rating})'
