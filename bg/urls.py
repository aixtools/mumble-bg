"""Minimal URL stub for Django management compatibility."""

from django.http import HttpResponse
from django.urls import path


def _health(_request):
    return HttpResponse('ok')


urlpatterns = [
    path('', _health),
]
