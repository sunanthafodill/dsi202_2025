# orders/templatetags/order_tags.py
from django import template
from django.utils import timezone

register = template.Library()

@register.filter
def estimated_time_range(order_time):
    if not order_time:
        return "ไม่ระบุ"
    start_delta = timezone.timedelta(minutes=35)
    end_delta = timezone.timedelta(minutes=50)
    start_time = order_time + start_delta
    end_time = order_time + end_delta
    return f"{start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')} น."