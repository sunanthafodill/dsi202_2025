from django import template
from datetime import timedelta

register = template.Library()

@register.filter
def add_minutes(value, minutes):
    return value + timedelta(minutes=minutes)