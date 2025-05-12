from django import template

register = template.Library()

@register.filter
def split(value, delimiter):
    """Split a string by the given delimiter and return a list."""
    if isinstance(value, str):
        return value.split(delimiter)
    return value

@register.filter
def strip(value):
    """Remove leading and trailing whitespace from a string."""
    if isinstance(value, str):
        return value.strip()
    return value