from django.shortcuts import render
from django.http import Http404
from django.db.models import Count



def error_404_view(request, exception=None):
    """Render custom 404 page."""
    return render(request, '404.html', status=404)


def error_500_view(request):
    """Render custom 500 page."""
    return render(request, '500.html', status=500)


def error_403_view(request, exception=None):
    """Render custom 403 page."""
    return render(request, '403.html', status=403)


def error_400_view(request, exception=None):
    """Render custom 400 page."""
    return render(request, '400.html', status=400)

