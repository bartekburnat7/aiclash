from django.db import models


class SiteSettings(models.Model):
    """Singleton model for global site settings editable from admin."""

    solana_ca = models.CharField(
        max_length=64,
        blank=True,
        default='',
        verbose_name='Solana Contract Address',
        help_text='The token CA shown on the homepage. Update here to reflect instantly.',
    )

    class Meta:
        verbose_name = 'Site Settings'
        verbose_name_plural = 'Site Settings'

    def __str__(self):
        return 'Site Settings'

    def save(self, *args, **kwargs):
        # Enforce singleton — always use pk=1
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
