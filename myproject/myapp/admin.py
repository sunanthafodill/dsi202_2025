from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.db.models import Avg, Count
from .models import Tag, Allergy, Address, Store, Order, OrderItem, Delivery, Review, Cart, Profile
from .forms import StoreAdminForm

class AllergyInline(admin.TabularInline):
    model = Allergy
    extra = 1
    fields = ('name',)

class AddressInline(admin.TabularInline):
    model = Address
    extra = 1
    fields = ('label', 'address_line', 'subdistrict', 'district', 'province', 'postal_code', 'phone_number', 'is_default')
    readonly_fields = ()

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 1
    fields = ('store', 'quantity', 'price', 'note')
    readonly_fields = ('price',)

class ReviewInline(admin.TabularInline):
    model = Review
    extra = 1
    fields = ('user', 'rating', 'comment', 'review_date')
    readonly_fields = ('review_date',)

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'id')
    search_fields = ('name',)
    list_filter = ('name',)

@admin.register(Allergy)
class AllergyAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'id')
    list_filter = ('name',)
    search_fields = ('name', 'user__username', 'user__email')
    list_select_related = ('user',)

@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ('label', 'user', 'address_line', 'subdistrict', 'district', 'province', 'postal_code', 'phone_number', 'is_default', 'id')
    list_filter = ('province', 'district', 'is_default')
    search_fields = ('label', 'address_line', 'subdistrict', 'district', 'province', 'postal_code', 'phone_number', 'user__username')
    list_select_related = ('user',)
    list_editable = ('is_default',)

@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    form = StoreAdminForm
    list_display = ('name', 'price', 'discount_percentage', 'quantity_available', 'is_active', 'average_rating', 'total_reviews', 'id')
    list_filter = ('is_active', 'tags')
    search_fields = ('name', 'description', 'allergen_ingredients', 'additional_details')
    list_editable = ('is_active', 'quantity_available')
    inlines = [ReviewInline]
    filter_horizontal = ('tags',)
    fieldsets = (
        (None, {
            'fields': ('name', 'tags', 'description', 'additional_details')
        }),
        ('ราคาและความพร้อม', {
            'fields': ('price', 'discount_percentage', 'quantity_available', 'available_from', 'available_until', 'is_active')
        }),
        ('รูปภาพ', {
            'fields': ('store_image', 'additional_images')
        }),
        ('สารก่อภูมิแพ้', {
            'fields': ('allergen_ingredients',)
        }),
    )
    def average_rating(self, obj):
        result = obj.reviews.aggregate(avg_rating=Avg('rating'))
        avg_rating = result['avg_rating']
        return f"{avg_rating:.1f}/5" if avg_rating else "ยังไม่มีรีวิว"
    def total_reviews(self, obj):
        return obj.reviews.count()
    average_rating.short_description = 'คะแนนเฉลี่ย'
    total_reviews.short_description = 'จำนวนรีวิว'
    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('reviews', 'tags')

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'buyer', 'delivery_address', 'total_price', 'total_with_shipping', 'status', 'order_time', 'estimated_time')
    list_filter = ('status', 'order_time', 'payment_method')
    search_fields = ('id', 'buyer__username', 'delivery_address__label')
    list_select_related = ('buyer', 'delivery_address')
    inlines = [OrderItemInline]
    readonly_fields = ('order_time',)
    fieldsets = (
        (None, {
            'fields': ('buyer', 'delivery_address', 'total_price', 'shipping_fee', 'total_with_shipping', 'payment_method', 'status', 'estimated_time')
        }),
        ('Timestamps', {
            'fields': ('order_time',)
        }),
    )

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'store', 'quantity', 'price', 'note', 'id')
    list_filter = ('store',)
    search_fields = ('order__id', 'store__name')
    list_select_related = ('order', 'store')
    readonly_fields = ('price',)

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

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('store', 'user', 'rating', 'comment', 'review_date', 'id')
    list_filter = ('rating', 'review_date')
    search_fields = ('store__name', 'user__username', 'comment')
    list_select_related = ('store', 'user')
    readonly_fields = ('review_date',)

@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('user', 'store', 'quantity', 'note', 'created_at', 'id')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'store__name')
    list_select_related = ('user', 'store')

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone_number')
    search_fields = ('user__username', 'phone_number')
    list_select_related = ('user',)

class CustomUserAdmin(UserAdmin):
    inlines = [AllergyInline, AddressInline]

admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)