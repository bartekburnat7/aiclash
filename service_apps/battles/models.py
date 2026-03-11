from django.db import models
from django.conf import settings


class Battle(models.Model):
    STATUS_WAITING = 'waiting'
    STATUS_PENDING = 'pending'
    STATUS_JUDGING = 'judging'
    STATUS_FINISHED = 'finished'

    STATUS_CHOICES = [
        (STATUS_WAITING, 'Waiting'),
        (STATUS_PENDING, 'Pending'),
        (STATUS_JUDGING, 'Judging'),
        (STATUS_FINISHED, 'Finished'),
    ]

    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='posted_battles',
    )
    player_a = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='player_a_battles',
    )
    player_b = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='player_b_battles',
    )

    topic = models.CharField(max_length=400)
    stake = models.DecimalField(max_digits=10, decimal_places=4, default=0.1)

    player_a_prompt = models.TextField(blank=True)
    player_b_prompt = models.TextField(blank=True)

    player_a_response = models.TextField(blank=True)
    player_b_response = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_WAITING)

    winner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='won_battles',
    )
    judge_reasoning = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        a = self.player_a.username if self.player_a else '?'
        b = self.player_b.username if self.player_b else '?'
        return f'Battle #{self.pk}: {a} vs {b} — {self.topic[:50]}'
