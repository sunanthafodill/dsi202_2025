from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.utils import timezone
import uuid

class ThailandTimeField(models.DateTimeField):
    def pre_save(self, model_instance, add):
        value = super().pre_save(model_instance, add)
        if value is not None and timezone.is_naive(value):
            value = timezone.make_aware(value, timezone=timezone.get_default_timezone())
        return value

class Tag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=True)
    def __str__(self):
        return self.name
    class Meta:
        verbose_name = "แท็ก"
        verbose_name_plural = "แท็ก"
        indexes = [models.Index(fields=['name'])]

class Allergy(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='allergies')
    name = models.CharField(max_length=255)
    def __str__(self):
        return f"{self.user.username} - {self.name}"
    class Meta:
        verbose_name = "สารก่อภูมิแพ้"
        verbose_name_plural = "สารก่อภูมิแพ้"
        indexes = [models.Index(fields=['user', 'name'])]

class Address(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses')
    label = models.CharField(max_length=255, help_text="เช่น บ้าน, ที่ทำงาน")
    address_line = models.CharField(max_length=255, help_text="เลขที่, หมู่บ้าน, ถนน", default="")
    subdistrict = models.CharField(max_length=100, help_text="ตำบล/แขวง")
    district = models.CharField(max_length=100, help_text="อำเภอ/เขต")
    province = models.CharField(max_length=100, help_text="จังหวัด")
    postal_code = models.CharField(
        max_length=5,
        validators=[RegexValidator(r'^\d{5}$', 'รหัสไปรษณีย์ต้องเป็นตัวเลข 5 หลัก')],
        help_text="รหัสไปรษณีย์ 5 หลัก"
    )
    phone_number = models.CharField(
        max_length=10,
        validators=[RegexValidator(r'^\d{10}$', 'เบอร์โทรต้องเป็นตัวเลข 10 หลัก')],
        help_text="เบอร์โทร 10 หลัก"
    )
    is_default = models.BooleanField(default=False, help_text="ตั้งเป็นที่อยู่เริ่มต้น")
    def __str__(self):
        return f"{self.label} ({self.user.username})"
    def save(self, *args, **kwargs):
        if self.is_default:
            Address.objects.filter(user=self.user, is_default=True).exclude(id=self.id).update(is_default=False)
        super().save(*args, **kwargs)
    class Meta:
        verbose_name = "ที่อยู่"
        verbose_name_plural = "ที่อยู่"
        indexes = [models.Index(fields=['user', 'is_default'])]

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone_number = models.CharField(
        max_length=10,
        blank=True,
        validators=[RegexValidator(r'^\d{10}$', 'เบอร์โทรต้องเป็นตัวเลข 10 หลัก')],
        help_text="เบอร์โทร 10 หลัก (ถ้ามี)"
    )
    def __str__(self):
        return f"โปรไฟล์ของ {self.user.username}"
    class Meta:
        verbose_name = "โปรไฟล์"
        verbose_name_plural = "โปรไฟล์"
        indexes = [models.Index(fields=['user'])]

class Store(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField()
    additional_details = models.TextField(
        blank=True,
        help_text="รายละเอียดเพิ่มเติม เช่น นโยบายลดขยะอาหาร"
    )
    price = models.FloatField(validators=[MinValueValidator(0.0)])
    discount_percentage = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)],
        default=0.0,
        help_text="เปอร์เซ็นต์ส่วนลด (0-100%)"
    )
    quantity_available = models.PositiveIntegerField()
    available_from = models.TimeField(
        help_text="เวลาเปิดร้าน (เช่น 12:00)"
    )
    available_until = models.TimeField(
        help_text="เวลาปิดร้าน (เช่น 20:00)"
    )
    is_active = models.BooleanField(default=True)
    store_image = models.ImageField(upload_to='store_images/', null=True, blank=True)
    additional_images = models.JSONField(
        default=list,
        blank=True,
        help_text="รายการ URL หรือ path ของรูปภาพเพิ่มเติม"
    )
    allergen_ingredients = models.TextField(
        blank=True,
        help_text="ส่วนผสมที่อาจก่อให้เกิดอาการแพ้ (เช่น ถั่ว, กลูเตน)"
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name='stores')
    def __str__(self):
        return self.name
    @property
    def discounted_price(self):
        return self.price * (1 - (self.discount_percentage or 0) / 100)
    class Meta:
        verbose_name = "ร้านค้า"
        verbose_name_plural = "ร้านค้า"
        indexes = [models.Index(fields=['name', 'is_active'])]

class Review(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews')
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='reviews')
    rating = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True,
        blank=True
    )
    comment = models.TextField(blank=True)
    review_date = ThailandTimeField(auto_now_add=True)
    def __str__(self):
        return f"รีวิวโดย {self.user.username} สำหรับ {self.store.name}"
    class Meta:
        verbose_name = "รีวิว"
        verbose_name_plural = "รีวิว"
        unique_together = ['user', 'store']
        indexes = [models.Index(fields=['store', 'user', 'review_date'])]

class Cart(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    store = models.ForeignKey(Store, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    note = models.TextField(blank=True, default='')
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
        verbose_name = "ตะกร้า"
        verbose_name_plural = "ตะกร้า"
        unique_together = ['user', 'store']
        indexes = [models.Index(fields=['user', 'store'])]

class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'รอดำเนินการ'),
        ('confirmed', 'ยืนยันแล้ว'),
        ('out_for_delivery', 'กำลังจัดส่ง'),
        ('completed', 'สำเร็จ'),
        ('cancelled', 'ยกเลิก'),
    ]
    PAYMENT_METHODS = [
        ('bank_transfer', 'โอนเงิน'),
        ('credit_card', 'บัตรเครดิต'),
        ('cash_on_delivery', 'เงินสดเมื่อรับ'),
        ('promptpay', 'พร้อมเพย์'),
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
    estimated_time = ThailandTimeField(null=True, blank=True)
    def __str__(self):
        return f"คำสั่งซื้อ {self.id} โดย {self.buyer.username}"
    class Meta:
        verbose_name = "คำสั่งซื้อ"
        verbose_name_plural = "คำสั่งซื้อ"
        indexes = [models.Index(fields=['buyer', 'status', 'order_time'])]

    def save(self, *args, **kwargs):
        if not self.estimated_time and self.order_time:
            import random
            delta = timezone.timedelta(minutes=random.randint(35, 50))
            self.estimated_time = self.order_time + delta
        super().save(*args, **kwargs)

class OrderItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    store = models.ForeignKey(Store, on_delete=models.PROTECT, related_name='order_items')
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    price = models.FloatField(validators=[MinValueValidator(0.0)])
    note = models.TextField(blank=True, default='')
    def __str__(self):
        return f"{self.store.name} (x{self.quantity}) ในคำสั่งซื้อ {self.order.id}"
    class Meta:
        verbose_name = "รายการคำสั่งซื้อ"
        verbose_name_plural = "รายการคำสั่งซื้อ"
        indexes = [models.Index(fields=['order', 'store'])]

class Delivery(models.Model):
    STATUS_CHOICES = [
        ('pending', 'รอดำเนินการ'),
        ('assigned', 'มอบหมายแล้ว'),
        ('out_for_delivery', 'กำลังจัดส่ง'),
        ('completed', 'สำเร็จ'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='delivery')
    rider_id = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    pickup_time = ThailandTimeField(null=True, blank=True)
    delivery_time = ThailandTimeField(null=True, blank=True)
    def __str__(self):
        return f"การจัดส่งสำหรับคำสั่งซื้อ {self.order.id}"
    class Meta:
        verbose_name = "การจัดส่ง"
        verbose_name_plural = "การจัดส่ง"
        indexes = [models.Index(fields=['order', 'status'])]