from django.contrib import admin
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
    list_display = ('date', 'location', 'trip')
    list_filter = ('trip', 'date')

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('title', 'type', 'day', 'time', 'cost_booked', 'is_paid')
    list_filter = ('day__trip', 'type', 'is_paid')
    search_fields = ('title', 'notes')

@admin.register(GlobalExpense)
class GlobalExpenseAdmin(admin.ModelAdmin):
    list_display = ('title', 'expense_type', 'trip', 'total_amount')
    list_filter = ('trip', 'expense_type')

@admin.register(DiaryEntry)
class DiaryEntryAdmin(admin.ModelAdmin):
    list_display = ('day',)
    list_filter = ('day__trip',)

@admin.register(DiaryImage)
class DiaryImageAdmin(admin.ModelAdmin):
    list_display = ('diary_entry', 'caption')

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
    list_display = ('text', 'template', 'category')
    list_filter = ('template__user', 'category')
