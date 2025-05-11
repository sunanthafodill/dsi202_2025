from django import template

register = template.Library()

@register.filter
def split(value, delimiter):
    if value:
        return [item.strip() for item in value.split(delimiter)]
    return []