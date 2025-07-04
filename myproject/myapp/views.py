from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Prefetch, Q
from django.utils import timezone
from django.views.generic import ListView
from django.http import JsonResponse, Http404, HttpResponseBadRequest
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from .models import Store, Cart, Order, Address, Allergy, Review, Profile, OrderItem
from .forms import AddressForm, AllergyForm, ProfileForm
from django.contrib.auth.forms import UserCreationForm
from uuid import uuid4
from django.urls import reverse
from django.db.models import Sum, F, Q
from django.views.decorators.csrf import csrf_exempt
from datetime import timedelta
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.cache import never_cache
import logging
import libscrc  # เพิ่มสำหรับ QR Code
import qrcode  # เพิ่มสำหรับ QR Code
from PIL import Image  # เพิ่มสำหรับ QR Code
import io  # เพิ่มสำหรับ QR Code
import base64  # เพิ่มสำหรับ QR Code
from django.conf import settings  # เพิ่มเพื่อใช้ PROMPTPAY_MOBILE

logger = logging.getLogger(__name__)

# ค่าคงที่สำหรับ PromptPay QR Code
TAG_PAYLOAD_FORMAT_INDICATOR = "00"
TAG_POINT_OF_INITIATION_METHOD = "01"
TAG_MERCHANT_ACCOUNT_INFORMATION = "29"
SUB_TAG_AID_PROMPTPAY = "00"
SUB_TAG_MOBILE_NUMBER_PROMPTPAY = "01"
SUB_TAG_NATIONAL_ID_PROMPTPAY = "02"
TAG_TRANSACTION_CURRENCY = "53"
TAG_TRANSACTION_AMOUNT = "54"
TAG_COUNTRY_CODE = "58"
TAG_CRC = "63"

VALUE_PAYLOAD_FORMAT_INDICATOR = "01"
VALUE_POINT_OF_INITIATION_MULTIPLE = "11"
VALUE_POINT_OF_INITIATION_ONETIME = "12"
VALUE_PROMPTPAY_AID = "A000000677010111"
VALUE_COUNTRY_CODE_TH = "TH"
VALUE_CURRENCY_THB = "764"
LEN_CRC_VALUE_HEX = "04"

class QRError(Exception):
    pass

class InvalidInputError(QRError):
    pass

def _format_tlv(tag: str, value: str) -> str:
    length_str = f"{len(value):02d}"
    return f"{tag}{length_str}{value}"

def calculate_crc(code_string: str) -> str:
    try:
        encoded_string = str.encode(code_string, 'ascii')
    except UnicodeEncodeError:
        raise InvalidInputError("Payload contains non-ASCII characters.")
    crc_val = libscrc.ccitt_false(encoded_string)
    crc_hex_str = hex(crc_val)[2:].upper()
    return crc_hex_str.rjust(4, '0')

def generate_promptpay_qr_payload(mobile=None, nid=None, amount=None, one_time=False):
    if not mobile and not nid:
        raise InvalidInputError("Either mobile number or National ID (NID) must be provided.")
    if mobile and nid:
        raise InvalidInputError("Provide either mobile number or National ID (NID), not both.")

    payload_elements = [
        _format_tlv(TAG_PAYLOAD_FORMAT_INDICATOR, VALUE_PAYLOAD_FORMAT_INDICATOR),
        _format_tlv(TAG_POINT_OF_INITIATION_METHOD, VALUE_POINT_OF_INITIATION_ONETIME if one_time else VALUE_POINT_OF_INITIATION_MULTIPLE)
    ]

    merchant_account_sub_elements = [_format_tlv(SUB_TAG_AID_PROMPTPAY, VALUE_PROMPTPAY_AID)]
    if mobile:
        mobile_cleaned = mobile.strip()
        if not (len(mobile_cleaned) == 10 and mobile_cleaned.isdigit()):
            raise InvalidInputError("Mobile number must be a 10-digit string.")
        formatted_mobile_value = f"00{VALUE_COUNTRY_CODE_TH}{mobile_cleaned[1:]}"
        merchant_account_sub_elements.append(_format_tlv(SUB_TAG_MOBILE_NUMBER_PROMPTPAY, formatted_mobile_value))
    elif nid:
        nid_cleaned = nid.strip().replace('-', '')
        if not (len(nid_cleaned) == 13 and nid_cleaned.isdigit()):
            raise InvalidInputError("National ID (NID) must be a 13-digit string.")
        merchant_account_sub_elements.append(_format_tlv(SUB_TAG_NATIONAL_ID_PROMPTPAY, nid_cleaned))
    
    payload_elements.append(_format_tlv(TAG_MERCHANT_ACCOUNT_INFORMATION, "".join(merchant_account_sub_elements)))
    payload_elements.append(_format_tlv(TAG_TRANSACTION_CURRENCY, VALUE_CURRENCY_THB))

    if amount is not None:
        amount_str_eval = str(amount).strip()
        if amount_str_eval:
            try:
                amount_float = float(amount_str_eval)
                if amount_float != 0.0:
                    if amount_float < 0:
                        raise InvalidInputError("Transaction amount cannot be negative.")
                    formatted_amount_value = f"{amount_float:.2f}"
                    payload_elements.append(_format_tlv(TAG_TRANSACTION_AMOUNT, formatted_amount_value))
            except ValueError:
                raise InvalidInputError(f"Invalid amount value: '{amount}'.")

    payload_elements.append(_format_tlv(TAG_COUNTRY_CODE, VALUE_COUNTRY_CODE_TH))
    data_for_crc_calculation = "".join(payload_elements)
    string_to_calculate_crc_on = data_for_crc_calculation + TAG_CRC + LEN_CRC_VALUE_HEX
    crc_hex_value = calculate_crc(string_to_calculate_crc_on)
    return (string_to_calculate_crc_on + crc_hex_value).upper()

def generate_qr_image(payload):
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    return img_byte_arr.getvalue()

def signup(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            Profile.objects.create(user=user)
            messages.success(request, 'สมัครสมาชิกสำเร็จ! กรุณาเข้าสู่ระบบ.')
            return redirect('login')
        else:
            messages.error(request, 'เกิดข้อผิดพลาด กรุณาตรวจสอบข้อมูล.')
    else:
        form = UserCreationForm()
    context = {'form': form}
    context.update(base_context(request))
    return render(request, 'account/signup.html', context)

def base_context(request):
    cart_count = 0
    current_cart_store_id = None
    if request.user.is_authenticated:
        cart_items = Cart.objects.filter(user=request.user)
        cart_count = sum(item.quantity for item in cart_items)
        cart_item = cart_items.first()
        if cart_item:
            current_cart_store_id = str(cart_item.store.id)
    return {
        'cart_count': cart_count,
        'is_authenticated': request.user.is_authenticated,
        'current_cart_store_id': current_cart_store_id,
    }

def home(request):
    context = {
        'welcome_message': "ยินดีต้อนรับสู่ IMSUK",
        'mission_statement': "เรามุ่งมั่นลดขยะอาหารและต่อสู้เพื่อโลกที่ยั่งยืนด้วยความเห็นใจต่อผู้คนและร้านอาหาร",
    }
    context.update(base_context(request))
    return render(request, 'home.html', context)

logger = logging.getLogger(__name__)

class StoreListView(ListView):
    model = Store
    template_name = 'store_list.html'
    context_object_name = 'page_obj'
    paginate_by = 20

    def get_queryset(self):
        queryset = Store.objects.filter(is_active=True, quantity_available__gt=0)
        search_query = self.request.GET.get('search', '').strip()
        sort = self.request.GET.get('sort', '')

        if search_query:
            try:
                queryset = queryset.filter(
                    Q(name__icontains=search_query) |
                    Q(description__icontains=search_query) |
                    Q(additional_details__icontains=search_query)
                ).distinct()
            except Exception as e:
                logger.error(f"Search error: {str(e)}, query={search_query}")
                queryset = queryset.none()

        if sort:
            try:
                if sort == 'price_asc':
                    queryset = queryset.annotate(
                        calc_discounted_price=F('price') * (1 - F('discount_percentage') / 100.0)
                    ).order_by('calc_discounted_price', 'name')
                elif sort == 'price_desc':
                    queryset = queryset.annotate(
                        calc_discounted_price=F('price') * (1 - F('discount_percentage') / 100.0)
                    ).order_by('-calc_discounted_price', 'name')
                elif sort == 'discount_desc':
                    queryset = queryset.order_by('-discount_percentage', 'name')
                else:
                    logger.warning(f"Invalid sort parameter: {sort}")
            except Exception as e:
                logger.error(f"Sort error: {str(e)}, sort={sort}")

        logger.info(f"StoreListView: search={search_query}, sort={sort}, results={queryset.count()}")
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('search', '')
        context['sort'] = self.request.GET.get('sort', '')
        # Reset cart_store_id if cart is empty
        cart_count = Cart.objects.filter(user=self.request.user).count() if self.request.user.is_authenticated else 0
        if cart_count == 0:
            self.request.session.pop('cart_store_id', None)
            context['current_cart_store_id'] = ''
        else:
            context['current_cart_store_id'] = self.request.session.get('cart_store_id', '')
        return context

    def render_to_response(self, context):
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            try:
                page_obj = context['page_obj']
                html = render(self.request, 'store_grid_partial.html', {'page_obj': page_obj}).content.decode('utf-8')
                return JsonResponse({'html': html})
            except Exception as e:
                logger.error(f"AJAX render error: {str(e)}")
                return JsonResponse({'error': 'Render failed'}, status=500)
        return super().render_to_response(context)

class StoreDetailView(ListView):
    model = Store
    template_name = 'store_detail.html'
    context_object_name = 'stores'

    def get_queryset(self):
        store_id = self.kwargs['pk']
        current_time = timezone.localtime().time()
        queryset = Store.objects.filter(
            id=store_id,
            is_active=True,
            available_from__lte=current_time,
            available_until__gte=current_time
        ).prefetch_related(
            Prefetch('reviews', queryset=Review.objects.select_related('user').order_by('-review_date')),
            'tags'
        )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        store = self.get_queryset().first()
        if not store:
            raise Http404("Store not found or not available")
        
        context['store'] = store
        context['cart_quantity'] = 0
        if self.request.user.is_authenticated:
            cart_item = Cart.objects.filter(user=self.request.user, store=store).first()
            if cart_item:
                context['cart_quantity'] = cart_item.quantity
        context['related_stores'] = Store.objects.filter(
            tags__in=store.tags.all(),
            is_active=True
        ).exclude(id=store.id).distinct()[:3]
        context.update(base_context(self.request))
        return context

    def post(self, request, *args, **kwargs):
        if 'rating' in request.POST:
            return submit_review(request)
        return add_to_cart(request)

@require_POST
@login_required(login_url='login')
def add_to_cart(request):
    logger.debug(f"Add to cart request: method={request.method}, user={request.user}, POST={request.POST}")
    if request.method != 'POST':
        logger.error("Invalid request method")
        return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=400)

    store_id = request.POST.get('store_id')
    quantity = request.POST.get('quantity', '')
    logger.debug(f"Cart data: store_id={store_id}, quantity={quantity}")

    # Validate inputs
    if not store_id:
        logger.error("Missing store_id")
        return JsonResponse({'success': False, 'error': 'Missing store ID'}, status=400)

    try:
        quantity = int(quantity)
        if quantity < 0:
            logger.error(f"Negative quantity: {quantity}")
            return JsonResponse({'success': False, 'error': 'Quantity cannot be negative'}, status=400)
    except ValueError:
        logger.error(f"Invalid quantity format: {quantity}")
        return JsonResponse({'success': False, 'error': 'Invalid quantity format'}, status=400)

    # Get store
    try:
        store = Store.objects.get(id=store_id, is_active=True)
        if store.quantity_available < quantity:
            logger.error(f"Insufficient stock for store: {store_id}, requested={quantity}, available={store.quantity_available}")
            return JsonResponse({'success': False, 'error': 'Insufficient stock'}, status=400)
    except Store.DoesNotExist:
        logger.error(f"Store not found: {store_id}")
        return JsonResponse({'success': False, 'error': 'Store not found'}, status=400)

    # Check cart store consistency
    cart_count = Cart.objects.filter(user=request.user).count()
    if cart_count == 0:
        request.session.pop('cart_store_id', None)
    else:
        current_cart_store_id = request.session.get('cart_store_id')
        if current_cart_store_id and current_cart_store_id != str(store.id):
            logger.warning(f"Cart store mismatch: current={current_cart_store_id}, new={store.id}")
            return JsonResponse({
                'success': False,
                'error': 'You can only add items from one store at a time'
            }, status=400)

    try:
        cart, created = Cart.objects.get_or_create(
            user=request.user,
            store=store,
            defaults={'quantity': quantity}
        )
        if not created:
            if quantity == 0:
                cart.delete()
                request.session.pop('cart_store_id', None)
                message = 'Item removed from cart'
                logger.info(f"Removed from cart: user={request.user}, store={store.name}")
            else:
                cart.quantity = quantity
                cart.save()
                message = f'Added {quantity} {store.name} to cart'
                logger.info(f"Updated cart: user={request.user}, store={store.name}, quantity={quantity}")
        else:
            message = f'Added {quantity} {store.name} to cart'
            logger.info(f"Created cart: user={request.user}, store={store.name}, quantity={quantity}")

        request.session['cart_store_id'] = str(store.id) if quantity > 0 else None
        cart_count = Cart.objects.filter(user=request.user).aggregate(total_quantity=Sum('quantity'))['total_quantity'] or 0
        return JsonResponse({
            'success': True,
            'message': message,
            'cartQuantity': cart_count,
            'quantityAvailable': store.quantity_available
        })
    except Exception as e:
        logger.error(f"Add to cart error: {str(e)}, store_id={store_id}, user={request.user}")
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@login_required
def check_cart(request):
    try:
        cart_count = Cart.objects.filter(user=request.user).count()
        logger.debug(f"Cart check for user={request.user}, count={cart_count}")
        return JsonResponse({'cart_count': cart_count})
    except Exception as e:
        logger.error(f"Cart check error: {str(e)}, user={request.user}")
        return JsonResponse({'error': 'Failed to check cart'}, status=500)

@login_required(login_url='login')
def cart(request):
    if not request.user.is_authenticated:
        messages.warning(request, "กรุณาล็อกอินเพื่อดูตะกร้าสินค้า")
        return redirect('login')

    cart_items = Cart.objects.filter(user=request.user).select_related('store')
    user_allergies = Allergy.objects.filter(user=request.user).values_list('name', flat=True)
    total_price = sum(item.total_discounted_price for item in cart_items)
    shipping_fee = 5.0
    total_with_shipping = total_price + shipping_fee
    addresses = Address.objects.filter(user=request.user)
    cart_count = sum(item.quantity for item in cart_items)

    for item in cart_items:
        item.allergens = item.store.allergen_ingredients.split(',') if item.store.allergen_ingredients else []
        item.has_allergy_warning = False
        if item.allergens:
            allergens_list = [allergen.strip() for allergen in item.allergens if allergen.strip()]
            item.has_allergy_warning = any(allergen.lower() in [ua.lower() for ua in user_allergies] for allergen in allergens_list)

    if request.method == 'POST':
        if request.POST.get('clear_cart'):
            cart_items.delete()
            messages.success(request, "ตะกร้าถูกล้างเรียบร้อย")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': 'ตะกร้าถูกล้างเรียบร้อย'})
            return redirect('cart')

        store_id = request.POST.get('store_id')
        note = request.POST.get('note', '')
        try:
            quantity = int(request.POST.get('quantity', 0))
            store = get_object_or_404(Store, id=store_id)
            if store.quantity_available is not None and quantity > store.quantity_available:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': 'จำนวนที่เลือกเกินสต๊อก'})
                messages.error(request, "จำนวนที่เลือกเกินสต๊อก")
                return redirect('cart')
            cart_item = Cart.objects.filter(user=request.user).first()
            if cart_item and str(cart_item.store.id) != store_id:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'message': 'คุณต้องล้างตะกร้าก่อนเพิ่มสินค้าจากร้านใหม่',
                    })
                messages.error(request, "คุณต้องล้างตะกร้าก่อนเพิ่มสินค้าจากร้านใหม่")
                return redirect('cart')
            cart_item, created = Cart.objects.get_or_create(
                user=request.user,
                store=store,
                defaults={'quantity': quantity, 'note': note}
            )
            if not created:
                if quantity <= 0:
                    cart_item.delete()
                    message = f"ลบ {store.name} ออกจากตะกร้าเรียบร้อย"
                else:
                    cart_item.quantity = quantity
                    cart_item.note = note
                    cart_item.save()
                    message = f"อัปเดตจำนวน {store.name} เรียบร้อย"
            else:
                message = f"เพิ่ม {store.name} ลงตะกร้าเรียบร้อย"
            cart_count = sum(item.quantity for item in Cart.objects.filter(user=request.user))
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': message, 'cart_count': cart_count})
            messages.success(request, message)
        except (ValueError, Store.DoesNotExist) as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': f'คำขอไม่ถูกต้อง: {str(e)}'})
            messages.error(request, f"คำขอไม่ถูกต้อง: {str(e)}")

        return redirect('cart')

    context = {
        'cart_items': cart_items,
        'total_price': total_price,
        'shipping_fee': shipping_fee,
        'total_with_shipping': total_with_shipping,
        'addresses': addresses,
        'cart_count': cart_count,
    }
    return render(request, 'cart.html', context)

@login_required(login_url='login')
def checkout(request):
    if not request.user.is_authenticated:
        messages.warning(request, "กรุณาล็อกอินเพื่อดำเนินการชำระเงิน")
        return redirect('login')

    cart_items = Cart.objects.filter(user=request.user).select_related('store')
    total_price = sum(item.total_discounted_price or 0 for item in cart_items)
    shipping_fee = 5.0
    total_with_shipping = total_price + shipping_fee
    cart_count = sum(item.quantity for item in cart_items)

    if not cart_items:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'ตะกร้าของคุณว่างเปล่า'}, status=400)
        messages.warning(request, "ตะกร้าของคุณว่างเปล่า กรุณาเพิ่มสินค้าก่อนดำเนินการชำระเงิน")
        return redirect('store_list')

    addresses = Address.objects.filter(user=request.user)

    if request.method == 'POST':
        address_id = request.POST.get('address_id')
        payment_method = request.POST.get('payment_method')
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        checkout_action = request.headers.get('X-Checkout-Action')

        if not address_id or not payment_method:
            if is_ajax:
                return JsonResponse({'success': False, 'message': 'กรุณาเลือกที่อยู่จัดส่งและช่องทางการชำระเงิน'}, status=400)
            messages.error(request, "กรุณาเลือกที่อยู่จัดส่งและช่องทางการชำระเงิน")
            return render(request, 'cart.html', {
                'cart_items': cart_items,
                'total_price': total_price,
                'shipping_fee': shipping_fee,
                'total_with_shipping': total_with_shipping,
                'addresses': addresses,
                'cart_count': cart_count,
            })

        try:
            delivery_address = Address.objects.get(id=address_id, user=request.user)
        except Address.DoesNotExist:
            if is_ajax:
                return JsonResponse({'success': False, 'message': 'ที่อยู่จัดส่งไม่ถูกต้อง'}, status=400)
            messages.error(request, "ที่อยู่จัดส่งไม่ถูกต้อง")
            return render(request, 'cart.html', {
                'cart_items': cart_items,
                'total_price': total_price,
                'shipping_fee': shipping_fee,
                'total_with_shipping': total_with_shipping,
                'addresses': addresses,
                'cart_count': cart_count,
            })

        if is_ajax and checkout_action == 'validate' and payment_method == 'promptpay':
            try:
                # ใช้หมายเลขโทรศัพท์ของแพลตฟอร์มจาก settings
                mobile = settings.PROMPTPAY_MOBILE
                if not mobile:
                    logger.error("PROMPTPAY_MOBILE not configured in settings")
                    return JsonResponse({'success': False, 'message': 'ไม่สามารถสร้าง QR Code ได้ เนื่องจากไม่มีหมายเลขโทรศัพท์'}, status=400)
                
                # สร้าง QR Code
                payload = generate_promptpay_qr_payload(mobile=mobile, amount=total_with_shipping, one_time=True)
                qr_image = generate_qr_image(payload)
                qr_base64 = base64.b64encode(qr_image).decode('utf-8')
                qr_code_url = f"data:image/png;base64,{qr_base64}"
                
                logger.info(f"Generated QR code for amount={total_with_shipping}")
                return JsonResponse({
                    'success': True,
                    'total_with_shipping': float(total_with_shipping),
                    'qr_code_url': qr_code_url,
                    'message': 'QR Code พร้อมใช้งาน'
                })
            except InvalidInputError as e:
                logger.error(f"QR Code generation failed: {str(e)}")
                return JsonResponse({'success': False, 'message': str(e)}, status=400)
            except Exception as e:
                logger.error(f"Unexpected error in QR Code generation: {str(e)}")
                return JsonResponse({'success': False, 'message': 'เกิดข้อผิดพลาดในการสร้าง QR Code'}, status=500)

        if is_ajax and checkout_action == 'confirm' and payment_method == 'promptpay':
            try:
                order = Order.objects.create(
                    id=uuid4(),
                    buyer=request.user,
                    delivery_address=delivery_address,
                    total_price=total_price,
                    shipping_fee=shipping_fee,
                    total_with_shipping=total_with_shipping,
                    payment_method=payment_method,
                    status='confirmed',
                    estimated_time=timezone.now() + timedelta(minutes=25)
                )

                for item in cart_items:
                    OrderItem.objects.create(
                        order=order,
                        store=item.store,
                        quantity=item.quantity,
                        price=item.store.price,
                        note=item.note,
                    )

                cart_items.delete()
                logger.info(f"Order confirmed: id={order.id}, user={request.user}, method={payment_method}")
                return JsonResponse({
                    'success': True,
                    'message': f'สั่งซื้อสำเร็จ! หมายเลขคำสั่งซื้อ: {order.id}',
                    'redirect_url': reverse('checkout_success', kwargs={'order_id': str(order.id)})
                })
            except Exception as e:
                logger.error(f"Order confirmation failed: {str(e)}")
                return JsonResponse({'success': False, 'message': 'ไม่สามารถยืนยันคำสั่งซื้อได้'}, status=500)

        if payment_method != 'promptpay':
            try:
                order = Order.objects.create(
                    id=uuid4(),
                    buyer=request.user,
                    delivery_address=delivery_address,
                    total_price=total_price,
                    shipping_fee=shipping_fee,
                    total_with_shipping=total_with_shipping,
                    payment_method=payment_method,
                    status='confirmed' if payment_method == 'cash_on_delivery' else 'pending',
                    estimated_time=timezone.now() + timedelta(minutes=25)
                )

                for item in cart_items:
                    OrderItem.objects.create(
                        order=order,
                        store=item.store,
                        quantity=item.quantity,
                        price=item.store.price,
                        note=item.note,
                    )

                cart_items.delete()
                logger.info(f"Order created: id={order.id}, user={request.user}, method={payment_method}")
                messages.success(request, f"สั่งซื้อสำเร็จ! หมายเลขคำสั่งซื้อ: {order.id}")
                context = {'order': order, 'cart_count': 0}
                return render(request, 'checkout_success.html', context)
            except Exception as e:
                logger.error(f"Order creation failed: {str(e)}")
                messages.error(request, "ไม่สามารถดำเนินการสั่งซื้อได้")
                return render(request, 'cart.html', {
                    'cart_items': cart_items,
                    'total_price': total_price,
                    'shipping_fee': shipping_fee,
                    'total_with_shipping': total_with_shipping,
                    'addresses': addresses,
                    'cart_count': cart_count,
                })

        return redirect('checkout_success', order_id=order.id)

    context = {
        'cart_items': cart_items,
        'total_price': total_price,
        'shipping_fee': shipping_fee,
        'total_with_shipping': total_with_shipping,
        'addresses': addresses,
        'cart_count': cart_count,
    }
    return render(request, 'cart.html', context)

@login_required(login_url='login')
def checkout_success(request, order_id):
    order = get_object_or_404(Order, id=order_id, buyer=request.user)
    context = {'order': order}
    context.update(base_context(request))
    return render(request, 'checkout_success.html', context)

@login_required
def profile_settings(request):
    profile, created = Profile.objects.get_or_create(user=request.user)
    addresses = Address.objects.filter(user=request.user)
    allergies = Allergy.objects.filter(user=request.user)

    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        if form_type == 'profile':
            form = ProfileForm(request.POST, instance=profile)
            if form.is_valid():
                form.save()
                message = 'อัปเดตข้อมูลส่วนตัวเรียบร้อยแล้ว'
                if is_ajax:
                    return JsonResponse({'success': True, 'message': message})
                messages.success(request, message)
            else:
                message = 'เกิดข้อผิดพลาดในการอัปเดตข้อมูลส่วนตัว'
                if is_ajax:
                    return JsonResponse({'success': False, 'error': message}, status=400)
                messages.error(request, message)
        elif form_type == 'address':
            form = AddressForm(request.POST)
            if form.is_valid():
                address = form.save(commit=False)
                address.user = request.user
                address.save()
                message = 'เพิ่มที่อยู่เรียบร้อยแล้ว'
                if is_ajax:
                    return JsonResponse({'success': True, 'message': message})
                messages.success(request, message)
            else:
                message = 'เกิดข้อผิดพลาดในการเพิ่มที่อยู่'
                if is_ajax:
                    return JsonResponse({'success': False, 'error': message}, status=400)
                messages.error(request, message)
        elif form_type == 'edit_address':
            address_id = request.POST.get('address_id')
            try:
                address = Address.objects.get(id=address_id, user=request.user)
                form = AddressForm(request.POST, instance=address)
                if form.is_valid():
                    form.save()
                    message = 'แก้ไขที่อยู่เรียบร้อยแล้ว'
                    if is_ajax:
                        return JsonResponse({'success': True, 'message': message})
                    messages.success(request, message)
                else:
                    message = 'เกิดข้อผิดพลาดในการแก้ไขที่อยู่'
                    if is_ajax:
                        return JsonResponse({'success': False, 'error': message}, status=400)
                    messages.error(request, message)
            except Address.DoesNotExist:
                message = 'ไม่พบที่อยู่ที่ต้องการแก้ไข'
                if is_ajax:
                    return JsonResponse({'success': False, 'error': message}, status=404)
                messages.error(request, message)
        elif form_type == 'allergy':
            form = AllergyForm(request.POST)
            if form.is_valid():
                allergy = form.save(commit=False)
                allergy.user = request.user
                allergy.save()
                message = 'เพิ่มสารก่อภูมิแพ้เรียบร้อย'
                if is_ajax:
                    return JsonResponse({'success': True, 'message': message})
                messages.success(request, message)
            else:
                message = 'เกิดข้อผิดพลาดในการเพิ่มสารก่อภูมิแพ้'
                if is_ajax:
                    return JsonResponse({'success': False, 'error': message}, status=400)
                messages.error(request, message)
        elif form_type == 'delete_address':
            address_id = request.POST.get('address_id')
            try:
                address = Address.objects.get(id=address_id, user=request.user)
                if address.is_default and Address.objects.filter(user=request.user).count() > 1:
                    message = 'ไม่สามารถลบที่อยู่เริ่มต้นได้ กรุณาเลือกที่อยู่อื่นเป็นเริ่มต้นก่อน'
                    if is_ajax:
                        return JsonResponse({'success': False, 'error': message}, status=400)
                    messages.error(request, message)
                else:
                    address.delete()
                    message = 'ลบที่อยู่เรียบร้อย'
                    if is_ajax:
                        return JsonResponse({'success': True, 'message': message})
                    messages.success(request, message)
            except Address.DoesNotExist:
                message = 'ไม่พบที่อยู่ที่ต้องการลบ'
                if is_ajax:
                    return JsonResponse({'success': False, 'error': message}, status=404)
                messages.error(request, message)
        elif form_type == 'delete_allergy':
            allergy_id = request.POST.get('allergy_id')
            try:
                allergy = Allergy.objects.get(id=allergy_id, user=request.user)
                allergy.delete()
                message = 'ลบสารก่อภูมิแพ้เรียบร้อย'
                if is_ajax:
                    return JsonResponse({'success': True, 'message': message})
                messages.success(request, message)
            except Allergy.DoesNotExist:
                message = 'ไม่พบสารก่อภูมิแพ้ที่ต้องการลบ'
                if is_ajax:
                    return JsonResponse({'success': False, 'error': message}, status=404)
                messages.error(request, message)

        if is_ajax:
            return JsonResponse({'success': False, 'error': 'Invalid form type'}, status=400)
        return redirect('profile_settings')

    address_form = AddressForm()
    allergy_form = AllergyForm()
    profile_form = ProfileForm(instance=profile)
    context = {
        'profile': profile,
        'addresses': addresses,
        'allergies': allergies,
        'address_form': address_form,
        'allergy_form': allergy_form,
        'profile_form': profile_form,
    }
    context.update(base_context(request))
    return render(request, 'profile_settings.html', context)

@login_required
def order_history(request):
    orders = Order.objects.filter(buyer=request.user).prefetch_related(
        Prefetch('items', queryset=OrderItem.objects.select_related('store')),
        Prefetch('items__store__reviews', queryset=Review.objects.filter(user=request.user))
    ).order_by('-order_time')

    for order in orders:
        for item in order.items.all():
            review = item.store.reviews.filter(user=request.user).first()
            item.has_reviewed = bool(review)
            item.review_rating = review.rating if review else None
            item.store_detail_url = reverse('store_detail', kwargs={'pk': item.store.id})

    context = {
        'orders': orders,
    }
    context.update(base_context(request))
    return render(request, 'order_history.html', context)

@login_required(login_url='login')
def delete_order(request, order_id):
    try:
        order = Order.objects.get(id=order_id, buyer=request.user)
        order.delete()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'ลบคำสั่งซื้อเรียบร้อย'})
        messages.success(request, 'ลบคำสั่งซื้อเรียบร้อย')
    except Order.DoesNotExist:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'ไม่พบคำสั่งซื้อ'})
        messages.error(request, 'ไม่พบคำสั่งซื้อ')
    return redirect('order_history')

@csrf_exempt
def update_order_status(request, order_id):
    try:
        order = Order.objects.get(id=order_id)
        order.status = 'completed'
        order.save()
        # อัปเดต Delivery
        delivery, created = Delivery.objects.get_or_create(
            order=order,
            defaults={'rider_id': 'auto', 'status': 'completed', 'delivery_time': timezone.now()}
        )
        if not created and delivery.status != 'completed':
            delivery.status = 'completed'
            delivery.delivery_time = timezone.now()
            delivery.save()
        return JsonResponse({'success': True})
    except Order.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'ไม่พบคำสั่งซื้อ'}, status=404)

@require_POST
@login_required(login_url='login')
def submit_review(request):
    store_id = request.POST.get('store_id')
    rating = request.POST.get('rating')
    comment = request.POST.get('comment', '')
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    try:
        rating = int(rating)
        if not 1 <= rating <= 5:
            message = 'กรุณาให้คะแนนระหว่าง 1-5'
            return JsonResponse({'success': False, 'message': message}) if is_ajax else redirect('order_history')
        
        store = get_object_or_404(Store, id=store_id)
        
        # ตรวจสอบว่า user เคยซื้อจากร้านนี้
        order_item = OrderItem.objects.filter(
            order__buyer=request.user,
            store=store,
            order__status='completed',
            has_reviewed=False
        ).first()
        if not order_item:
            message = 'คุณต้องซื้อและรับสินค้าจากร้านนี้ก่อนจึงจะรีวิวได้'
            return JsonResponse({'success': False, 'message': message}) if is_ajax else redirect('order_history')
        
        # ตรวจสอบรีวิวซ้ำ
        if Review.objects.filter(user=request.user, store=store).exists():
            message = 'คุณรีวิวร้านนี้แล้ว'
            return JsonResponse({'success': False, 'message': message}) if is_ajax else redirect('order_history')
        
        # สร้าง Review และอัปเดต OrderItem
        Review.objects.create(
            user=request.user,
            store=store,
            rating=rating,
            comment=comment
        )
        order_item.has_reviewed = True
        order_item.review_rating = rating
        order_item.save()
        
        message = 'รีวิวสำเร็จ'
        return JsonResponse({'success': True, 'message': message}) if is_ajax else redirect('order_history')
    
    except (ValueError, Store.DoesNotExist) as e:
        message = f'เกิดข้อผิดพลาด: {str(e)}'
        return JsonResponse({'success': False, 'message': message}) if is_ajax else redirect('order_history')

def search_suggestions(request):
    query = request.GET.get('search', '').strip()
    suggestions = []
    if query:
        try:
            stores = Store.objects.filter(
                Q(name__icontains=query) |
                Q(description__icontains=query) |
                Q(additional_details__icontains=query),
                is_active=True,
                quantity_available__gt=0
            ).values('name').distinct()[:10]
            suggestions = [{'id': i, 'name': s['name']} for i, s in enumerate(stores)]
        except Exception as e:
            logger.error(f"Suggestions error: {str(e)}, query: {query}")
            suggestions = []
    logger.info(f"Search suggestions: query={query}, results={len(suggestions)}")
    return JsonResponse({'suggestions': suggestions})

@login_required
def get_address(request, address_id):
    address = get_object_or_404(Address, id=address_id, user=request.user)
    return JsonResponse({
        'label': address.label,
        'address_line': address.address_line,
        'subdistrict': address.subdistrict,
        'district': address.district,
        'province': address.province,
        'postal_code': address.postal_code,
        'phone_number': str(address.phone_number),
        'is_default': address.is_default,
    })

@csrf_exempt
@login_required
def delete_address(request, address_id):
    if request.method == 'POST':
        try:
            address = Address.objects.get(id=address_id, user=request.user)
            if address.is_default and Address.objects.filter(user=request.user).count() > 1:
                return JsonResponse({
                    'success': False,
                    'error': 'ไม่สามารถลบที่อยู่เริ่มต้นได้ กรุณาเลือกที่อยู่อื่นเป็นเริ่มต้นก่อน'
                }, status=400)
            address.delete()
            logger.info(f"Address deleted: id={address_id}, user={request.user}")
            return JsonResponse({'success': True, 'message': 'ลบที่อยู่สำเร็จ'})
        except Address.DoesNotExist:
            logger.error(f"Address not found: id={address_id}, user={request.user}")
            return JsonResponse({'success': False, 'error': 'ไม่พบที่อยู่'}, status=404)
        except Exception as e:
            logger.error(f"Delete address error: {str(e)}, address_id={address_id}, user={request.user}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    logger.warning(f"Invalid method for delete_address: method={request.method}, address_id={address_id}")
    return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)