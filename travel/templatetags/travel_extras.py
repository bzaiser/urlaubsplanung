import re
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter(name='magic_links')
def magic_links(value):
    if not value:
        return ""
    
    # Regex for [Name](URL)
    pattern = r'\[([^\]]+)\]\((https?://[^\s)]+)\)'
    
    # Replacement with HTML anchor
    # We add stopPropagation to avoid opening modals when clicking the link
    replacement = r'<a href="\2" target="_blank" onclick="event.stopPropagation()" class="text-warning text-decoration-underline fw-bold">\1</a>'
    
    result = re.sub(pattern, replacement, str(value))
    return mark_safe(result)
