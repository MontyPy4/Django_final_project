from rest_framework import serializers

from .models import Review


class ReviewSerializer(serializers.ModelSerializer):
    author = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Review
        fields = ('id', 'listing', 'author', 'rating', 'text', 'created_at')
        read_only_fields = ('id', 'author', 'created_at')

    def validate_rating(self, value):
        if not 1 <= value <= 5:
            raise serializers.ValidationError('Рейтинг должен быть от 1 до 5.')
        return value

    def validate(self, attrs):
        listing = attrs.get('listing') or getattr(self.instance, 'listing', None)
        if listing and not listing.is_active:
            raise serializers.ValidationError(
                {'listing': 'Нельзя оставить отзыв на неактивное объявление.'}
            )
        return attrs
