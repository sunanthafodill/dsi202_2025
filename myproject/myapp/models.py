from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid
from django.utils import timezone

# Set default timezone to Thailand (Asia/Bangkok)
class ThailandTimeField(models.DateTimeField):
    def pre_save(self, model_instance, add):
        value = super().pre_save(model_instance, add)
        if value is not None and timezone.is_naive(value):
            value = timezone.make_aware(value, timezone=timezone.get_default_timezone())
        return value

# Allergy Model
class Allergy(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='allergies')
    name = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.user.username} - {self.name}"

    class Meta:
        verbose_name = "Allergy"
        verbose_name_plural = "Allergies"

# Address Model
class Address(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses')
    label = models.CharField(max_length=255)
    address_line = models.TextField()
    city = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    latitude = models.FloatField()
    longitude = models.FloatField()

    def __str__(self):
        return f"{self.label} ({self.user.username})"

    class Meta:
        verbose_name = "Address"
        verbose_name_plural = "Addresses"

# Store Model
class Store(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField()
    additional_details = models.TextField(
        blank=True,
        help_text="Additional details, e.g., food waste reduction or store policies"
    )
    price = models.FloatField(validators=[MinValueValidator(0.0)])
    discount_percentage = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)],
        default=0.0,
        help_text="Discount percentage (0-100%)"
    )
    quantity_available = models.PositiveIntegerField()
    available_from = models.TimeField(
        help_text="Store opening time (e.g., 12:00)"
    )
    available_until = models.TimeField(
        help_text="Store closing time (e.g., 20:00)"
    )
    is_active = models.BooleanField(default=True)
    store_image = models.ImageField(upload_to='store_images/', null=True, blank=True)
    additional_images = models.JSONField(
        default=list,
        blank=True,
        help_text="List of URLs or paths for additional images"
    )
    allergen_ingredients = models.TextField(
        blank=True,
        help_text="Ingredients that may cause allergies (e.g., nuts, gluten)"
    )

    def __str__(self):
        return self.name

    @property
    def discounted_price(self):
        return self.price * (1 - (self.discount_percentage or 0) / 100)

    class Meta:
        verbose_name = "Store"
        verbose_name_plural = "Stores"

# Cart Model
class Cart(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    store = models.ForeignKey(Store, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    note = models.TextField(blank=True, default='')  # เพิ่มฟิลด์ note
    created_at = ThailandTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.store.name} (x{self.quantity})"

    @property
    def total_price(self):
        return self.store.price * self.quantity

    @property
    def total_discounted_price(self):
        return self.store.discounted_price * self.quantity

    class Meta:
        verbose_name = "Cart"
        verbose_name_plural = "Carts"

# Order Model
class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('out_for_delivery', 'Out for Delivery'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    PAYMENT_METHODS = [
        ('bank_transfer', 'โอนเงิน'),
        ('credit_card', 'บัตรเครดิต'),
        ('cash_on_delivery', 'เงินสดเมื่อรับ'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    buyer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    delivery_address = models.ForeignKey(Address, on_delete=models.PROTECT, related_name='orders', null=True)
    total_price = models.FloatField(validators=[MinValueValidator(0.0)])
    shipping_fee = models.FloatField(default=9.0, validators=[MinValueValidator(0.0)])
    total_with_shipping = models.FloatField(validators=[MinValueValidator(0.0)])
    payment_method = models.CharField(max_length=50, choices=PAYMENT_METHODS)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    order_time = ThailandTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order {self.id} by {self.buyer.username}"

    class Meta:
        verbose_name = "Order"
        verbose_name_plural = "Orders"

# OrderItem Model
class OrderItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    store = models.ForeignKey(Store, on_delete=models.PROTECT, related_name='order_items')
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    price = models.FloatField(validators=[MinValueValidator(0.0)])
    note = models.TextField(blank=True, default='')  # เพิ่มฟิลด์ note

    def __str__(self):
        return f"{self.store.name} (x{self.quantity}) in Order {self.order.id}"

    class Meta:
        verbose_name = "Order Item"
        verbose_name_plural = "Order Items"

# Delivery Model
class Delivery(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('assigned', 'Assigned'),
        ('out_for_delivery', 'Out for Delivery'),
        ('completed', 'Completed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='delivery')
    rider_id = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    pickup_time = ThailandTimeField(null=True, blank=True)
    delivery_time = ThailandTimeField(null=True, blank=True)

    def __str__(self):
        return f"Delivery for Order {self.order.id}"

    class Meta:
        verbose_name = "Delivery"
        verbose_name_plural = "Deliveries"

# Review Model
class Review(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews')
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='reviews')
    rating = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True,
        blank=True
    )
    review_date = ThailandTimeField(auto_now_add=True)

    def __str__(self):
        return f"Review by {self.user.username} for {self.store.name}"

    class Meta:
        verbose_name = "Review"
        verbose_name_plural = "Reviews"