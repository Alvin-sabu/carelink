from django import template
from decimal import Decimal

register = template.Library()

@register.filter(name='celsius_to_fahrenheit')
def celsius_to_fahrenheit(celsius):
    if celsius is None:
        return None
    return float(celsius) * 9/5 + 32

@register.filter(name='multiply')
def multiply(value, arg):
    if value is None:
        return None
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return None

@register.filter(name='add')
def add(value, arg):
    if value is None:
        return None
    try:
        return float(value) + float(arg)
    except (ValueError, TypeError):
        return None

@register.filter
def get_item(dictionary, key):
    """
    Template filter to get an item from a dictionary using a key.
    Usage: {{ dictionary|get_item:key }}
    """
    if dictionary is None:
        return None
    if not isinstance(dictionary, dict):
        return None
    
    # Convert key to string if it's not already
    str_key = str(key)
    return dictionary.get(str_key) 