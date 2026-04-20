from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import (
    Trip, Day, Event, GlobalExpense, DiaryEntry, DiaryImage, 
    TripTemplate, GlobalSetting, ChecklistTemplate, ChecklistItemTemplate
)

@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'start_date', 'end_date', 'persons_count')
    list_filter = ('user', 'start_date')
    search_fields = ('name',)

@admin.register(Day)
class DayAdmin(admin.ModelAdmin):
    list_display = ('date', 'get_user', 'location', 'trip')
    list_filter = ('trip__user', 'date')
    
    def get_user(self, obj):
        return obj.trip.user
    get_user.short_description = _("Benutzer")
    get_user.admin_order_field = 'trip__user'

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('title', 'get_user', 'type', 'day', 'time', 'cost_booked', 'is_paid')
    list_filter = ('day__trip__user', 'type', 'is_paid')
    search_fields = ('title', 'notes')

    def get_user(self, obj):
        return obj.day.trip.user
    get_user.short_description = _("Benutzer")
    get_user.admin_order_field = 'day__trip__user'

@admin.register(GlobalExpense)
class GlobalExpenseAdmin(admin.ModelAdmin):
    list_display = ('title', 'get_user', 'expense_type', 'trip', 'total_amount')
    list_filter = ('trip__user', 'expense_type')

    def get_user(self, obj):
        return obj.trip.user
    get_user.short_description = _("Benutzer")
    get_user.admin_order_field = 'trip__user'

@admin.register(DiaryEntry)
class DiaryEntryAdmin(admin.ModelAdmin):
    list_display = ('day', 'get_user')
    list_filter = ('day__trip__user',)

    def get_user(self, obj):
        return obj.day.trip.user
    get_user.short_description = _("Benutzer")

@admin.register(DiaryImage)
class DiaryImageAdmin(admin.ModelAdmin):
    list_display = ('diary_entry', 'get_user', 'caption')
    list_filter = ('diary_entry__day__trip__user',)

    def get_user(self, obj):
        return obj.diary_entry.day.trip.user
    get_user.short_description = _("Benutzer")

@admin.register(TripTemplate)
class TripTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'created_at')
    list_filter = ('user', 'created_at')

@admin.register(GlobalSetting)
class GlobalSettingAdmin(admin.ModelAdmin):
    list_display = ('key', 'user', 'value')
    list_filter = ('user', 'key')

@admin.register(ChecklistTemplate)
class ChecklistTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'user')
    list_filter = ('user',)

@admin.register(ChecklistItemTemplate)
class ChecklistItemTemplateAdmin(admin.ModelAdmin):
    list_display = ('text', 'get_user', 'template', 'category')
    list_filter = ('template__user', 'category')

    def get_user(self, obj):
        return obj.template.user
    get_user.short_description = _("Benutzer")
