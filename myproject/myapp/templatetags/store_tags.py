from django import template

register = template.Library()

@register.filter
def split(value, delimiter=','):
    if not isinstance(value, str):
        return []
    return [item.strip() for item in value.split(delimiter) if item.strip()]

@register.filter
def strip(value):
    return value.strip() if isinstance(value, str) else value