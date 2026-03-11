from django.urls import path
from . import views

app_name = 'battles'

urlpatterns = [
    path('', views.battle_list, name='list'),
    path('create/', views.create_battle, name='create'),
    path('generate-question/', views.generate_question, name='generate-question'),
    path('<int:pk>/', views.battle_detail, name='detail'),
    path('<int:pk>/join/', views.join_battle, name='join'),
    path('<int:pk>/prompt/', views.submit_prompt, name='submit-prompt'),
]
