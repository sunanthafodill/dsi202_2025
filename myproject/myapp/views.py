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

logger = logging.getLogger(__name__)

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

    cart_items = Cart.objects.filter(user=request.user)
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
                return JsonResponse({'success': False, 'message': 'กรุณาเลือกที่อยู่จัดส่งและช่องทางชำระเงิน'}, status=400)
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
            qr_code_url = 'https://via.placeholder.com/200'
            return JsonResponse({
                'success': True,
                'total_with_shipping': float(total_with_shipping),
                'qr_code_url': qr_code_url
            })

        if is_ajax and checkout_action == 'confirm' and payment_method == 'promptpay':
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
            return JsonResponse({
                'success': True,
                'message': f'สั่งซื้อสำเร็จ! หมายเลขคำสั่งซื้อ: {order.id}',
                'redirect_url': reverse('checkout_success', kwargs={'order_id': str(order.id)})
            })

        if payment_method != 'promptpay':
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
            messages.success(request, f"สั่งซื้อสำเร็จ! หมายเลขคำสั่งซื้อ: {order.id}")
            context = {'order': order, 'cart_count': 0}
            return render(request, 'checkout_success.html', context)

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
        if form_type == 'profile':
            form = ProfileForm(request.POST, instance=profile)
            if form.is_valid():
                form.save()
                messages.success(request, 'อัปเดตข้อมูลส่วนตัวเรียบร้อยแล้ว')
            else:
                messages.error(request, 'เกิดข้อผิดพลาดในการอัปเดตข้อมูลส่วนตัว')
        elif form_type == 'address':
            form = AddressForm(request.POST)
            if form.is_valid():
                address = form.save(commit=False)
                address.user = request.user
                address.save()
                messages.success(request, 'เพิ่มที่อยู่เรียบร้อยแล้ว')
            else:
                messages.error(request, 'เกิดข้อผิดพลาดในการเพิ่มที่อยู่')
        elif form_type == 'allergy':
            form = AllergyForm(request.POST)
            if form.is_valid():
                allergy = form.save(commit=False)
                allergy.user = request.user
                allergy.save()
                messages.success(request, 'เพิ่มสารก่อภูมิแพ้เรียบร้อย')
            else:
                messages.error(request, 'เกิดข้อผิดพลาดในการเพิ่มสารก่อภูมิแพ้')
        elif form_type == 'delete_address':
            address_id = request.POST.get('address_id')
            try:
                address = Address.objects.get(id=address_id, user=request.user)
                address.delete()
                messages.success(request, 'ลบที่อยู่เรียบร้อย')
            except Address.DoesNotExist:
                messages.error(request, 'ไม่พบที่อยู่ที่ต้องการลบ')
        elif form_type == 'delete_allergy':
            allergy_id = request.POST.get('allergy_id')
            try:
                allergy = Allergy.objects.get(id=allergy_id, user=request.user)
                allergy.delete()
                messages.success(request, 'ลบสารก่อภูมิแพ้เรียบร้อย')
            except Allergy.DoesNotExist:
                messages.error(request, 'ไม่พบสารก่อภูมิแพ้ที่ต้องการลบ')
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
            if is_ajax:
                return JsonResponse({'success': False, 'message': message})
            messages.error(request, message)
            return redirect('store_detail', pk=store_id)
        
        store = get_object_or_404(Store, id=store_id)
        
        # ตรวจสอบว่า user เคยซื้อจากร้านนี้
        has_purchased = Order.objects.filter(
            buyer=request.user,
            items__store=store
        ).exists()
        if not has_purchased:
            message = 'คุณต้องซื้อจากร้านนี้ก่อนจึงจะรีวิวได้'
            if is_ajax:
                return JsonResponse({'success': False, 'message': message})
            messages.error(request, message)
            return redirect('store_detail', pk=store_id)
        
        # ตรวจสอบรีวิวซ้ำ
        if Review.objects.filter(user=request.user, store=store).exists():
            message = 'คุณรีวิวร้านนี้แล้ว'
            if is_ajax:
                return JsonResponse({'success': False, 'message': message})
            messages.error(request, message)
            return redirect('store_detail', pk=store_id)
        
        Review.objects.create(
            user=request.user,
            store=store,
            rating=rating,
            comment=comment
        )
        message = 'รีวิวสำเร็จ'
        if is_ajax:
            return JsonResponse({'success': True, 'message': message})
        messages.success(request, message)
        return redirect('store_detail', pk=store_id)
    
    except (ValueError, Store.DoesNotExist) as e:
        message = f'เกิดข้อผิดพลาด: {str(e)}'
        if is_ajax:
            return JsonResponse({'success': False, 'message': message})
        messages.error(request, message)
        return redirect('store_detail', pk=store_id)

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