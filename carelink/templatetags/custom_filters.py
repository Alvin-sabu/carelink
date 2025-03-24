from django import template

register = template.Library()

@register.filter
def filter_status(queryset, status):
    """Filter a queryset by status field"""
    return [obj for obj in queryset if obj.status == status]

@register.filter
def exclude_id(queryset, id_to_exclude):
    """Exclude an object from queryset by id"""
    return [obj for obj in queryset if obj.id != id_to_exclude]
