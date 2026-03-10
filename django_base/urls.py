"""
URL configuration for django_base project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.urls import path, include
from django.contrib import admin
from django_base import views as main_views

urlpatterns = [
    path('', main_views.home, name='home'),
    path('admin/', admin.site.urls),
    path('account/', include('service_apps.account.urls')),
]

# Custom error handlers
handler404 = 'django_base.views.error_404_view'
handler500 = 'django_base.views.error_500_view'
handler403 = 'django_base.views.error_403_view'
handler400 = 'django_base.views.error_400_view'
