from django.contrib import admin
from .models import Battle


@admin.register(Battle)
class BattleAdmin(admin.ModelAdmin):
    list_display = ('id', 'posted_by', 'player_a', 'player_b', 'topic', 'stake', 'status', 'winner', 'created_at')
    list_filter = ('status',)
    search_fields = ('topic', 'posted_by__username', 'player_a__username', 'player_b__username')
    readonly_fields = ('player_a_response', 'player_b_response', 'judge_reasoning', 'created_at', 'updated_at')
