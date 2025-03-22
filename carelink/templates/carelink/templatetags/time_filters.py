from django import template

register = template.Library()

@register.filter(name='timedelta')
def format_timedelta(value):
    """
    Format a timedelta object into a human-readable string
    Example: '2 hours 30 minutes'
    """
    if not value:
        return ''
    
    total_minutes = int(value.total_seconds() / 60)
    hours = total_minutes // 60
    minutes = total_minutes % 60
    
    parts = []
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    
    return ' '.join(parts) if parts else 'less than a minute'