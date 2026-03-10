from django.db import models
from django.contrib.auth.models import AbstractUser

class CustomUser(AbstractUser):
    public_wallet_address=models.CharField(max_length=100)
    private_wallet_address=models.CharField(max_length=100)
    mnemonic_seed=models.CharField(max_length=255)
    
    groups = models.ManyToManyField(
        'auth.Group',
        related_name='customuser_set',
        blank=True,
        help_text='The groups this user belongs to.',
        verbose_name='groups'
    )
    
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='customuser_set',
        blank=True,
        help_text='Specific permissions for this user.',
        verbose_name='user permissions'
    )
