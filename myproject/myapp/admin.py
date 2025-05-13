from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from .models import Allergy, Address, Store, Order, OrderItem, Delivery, Review, Cart, Profile
from .forms import StoreAdminForm

# Inline for Allergy
class AllergyInline(admin.TabularInline):
    model = Allergy
    extra = 1
    fields = ('name',)

# Inline for Address
class AddressInline(admin.TabularInline):
    model = Address
    extra = 1
    fields = ('label', 'subdistrict', 'district', 'province', 'postal_code', 'phone_number')

# Inline for OrderItem
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 1
    fields = ('store', 'quantity', 'price')
    readonly_fields = ('price',)

# Inline for Review
class ReviewInline(admin.TabularInline):
    model = Review
    extra = 1
    fields = ('user', 'rating', 'review_date')
    readonly_fields = ('review_date',)

# Admin for Allergy
@admin.register(Allergy)
class AllergyAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'id')
    list_filter = ('name',)
    search_fields = ('name', 'user__username', 'user__email')
    list_select_related = ('user',)

# Admin for Address
@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ('label', 'user', 'subdistrict', 'district', 'province', 'postal_code', 'phone_number', 'id')
    list_filter = ('province', 'district')
    search_fields = ('label', 'subdistrict', 'district', 'province', 'postal_code', 'phone_number', 'user__username')
    list_select_related = ('user',)

# Admin for Store
@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    form = StoreAdminForm
    list_display = ('name', 'price', 'discount_percentage', 'quantity_available', 'is_active', 'id')
    list_filter = ('is_active',)
    search_fields = ('name', 'description', 'allergen_ingredients', 'additional_details')
    list_editable = ('is_active',)
    fieldsets = (
        (None, {
            'fields': ('name', 'description', 'additional_details')
        }),
        ('Price and Availability', {
            'fields': ('price', 'discount_percentage', 'quantity_available', 'available_from', 'available_until', 'is_active')
        }),
        ('Images', {
            'fields': ('store_image', 'additional_images', 'additional_images_upload')
        }),
        ('Allergens', {
            'fields': ('allergen_ingredients',)
        }),
    )

# Admin for Order
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'buyer', 'delivery_address', 'total_price', 'status', 'order_time')
    list_filter = ('status', 'order_time')
    search_fields = ('buyer__username', 'delivery_address__label', 'id')
    list_select_related = ('buyer', 'delivery_address')
    inlines = [OrderItemInline]
    readonly_fields = ('order_time',)
    fieldsets = (
        (None, {
            'fields': ('buyer', 'delivery_address', 'total_price', 'status')
        }),
        ('Timestamps', {
            'fields': ('order_time',)
        }),
    )

# Admin for OrderItem
@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'store', 'quantity', 'price', 'id')
    list_filter = ('store__name',)
    search_fields = ('order__id', 'store__name')
    list_select_related = ('order', 'store')
    readonly_fields = ('price',)

# Admin for Delivery
@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = ('order', 'rider_id', 'status', 'pickup_time', 'delivery_time', 'id')
    list_filter = ('status',)
    search_fields = ('order__id', 'rider_id')
    list_select_related = ('order',)
    readonly_fields = ('pickup_time', 'delivery_time')
    fieldsets = (
        (None, {
            'fields': ('order', 'rider_id', 'status')
        }),
        ('Timestamps', {
            'fields': ('pickup_time', 'delivery_time')
        }),
    )

# Admin for Review
@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('store', 'user', 'rating', 'review_date', 'id')
    list_filter = ('rating', 'review_date')
    search_fields = ('store__name', 'user__username')
    list_select_related = ('store', 'user')
    readonly_fields = ('review_date',)

# Admin for Cart
@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('user', 'store', 'quantity', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'store__name')
    list_select_related = ('user', 'store')

# Admin for Profile
@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone_number')
    search_fields = ('user__username', 'phone_number')
    list_select_related = ('user',)

# Customize User admin to include related models
class CustomUserAdmin(UserAdmin):
    inlines = [AllergyInline, AddressInline]

# Unregister the default User admin and register the custom one
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)