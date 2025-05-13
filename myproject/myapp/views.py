from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import ListView, DetailView
from django.http import JsonResponse
from django.contrib import messages
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from .models import Store, Cart, Order, Address, Allergy, Profile
from .forms import AddressForm, AllergyForm, ProfileForm
from django.contrib.auth.forms import UserCreationForm

def signup(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            Profile.objects.create(user=user)  # สร้าง Profile อัตโนมัติเมื่อสมัครสมาชิก
            messages.success(request, 'สมัครสมาชิกสำเร็จ! กรุณาเข้าสู่ระบบ.')
            return redirect('login')
        else:
            messages.error(request, 'เกิดข้อผิดพลาด กรุณาตรวจสอบข้อมูล.')
    else:
        form = UserCreationForm()
    return render(request, 'account/signup.html', {'form': form})

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
        'mission_statement': "เรามุ่งมั่นลดขยะอาหารและต่อสู้กับภาวะโลกร้อนด้วยความเห็นอกเห็นใจต่อโลก ผู้คน และร้านอาหาร",
    }
    context.update(base_context(request))
    return render(request, 'home.html', context)

class StoreListView(ListView):
    model = Store
    template_name = 'store_list.html'
    context_object_name = 'stores'
    paginate_by = 9

    def get_queryset(self):
        queryset = Store.objects.filter(is_active=True)
        current_time = timezone.localtime(timezone.now()).time()
        queryset = queryset.filter(
            available_from__lte=current_time,
            available_until__gte=current_time
        )
        search_query = self.request.GET.get('search', '').strip()
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(description__icontains=search_query)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('search', '')
        context.update(base_context(self.request))
        return context

    def post(self, request, *args, **kwargs):
        return add_to_cart(request)

class StoreDetailView(DetailView):
    model = Store
    template_name = 'store_detail.html'
    context_object_name = 'store'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['store'].additional_images = self.object.additional_images or []
        cart_quantity = 0
        if self.request.user.is_authenticated:
            cart_item = Cart.objects.filter(user=self.request.user, store=self.object).first()
            if cart_item:
                cart_quantity = cart_item.quantity
        context['cart_quantity'] = cart_quantity
        context.update(base_context(self.request))
        return context

    def post(self, request, *args, **kwargs):
        return add_to_cart(request)

@require_POST
@login_required(login_url='login')
def add_to_cart(request):
    store_id = request.POST.get('store_id')
    note = request.POST.get('note', '')
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'จำนวนไม่ถูกต้อง'})
        messages.error(request, "จำนวนไม่ถูกต้อง")
        return redirect('store_list')

    try:
        store = Store.objects.get(id=store_id)
    except Store.DoesNotExist:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'ร้านค้าไม่พบ'})
        messages.error(request, "ร้านค้าไม่พบ")
        return redirect('store_list')

    if quantity < 0:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'จำนวนต้องไม่น้อยกว่า 0'})
        messages.error(request, "จำนวนต้องไม่น้อยกว่า 0")
        return redirect('store_list')
    if store.quantity_available is not None and quantity > store.quantity_available:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'จำนวนที่เลือกเกินสต็อกที่มี'})
        messages.error(request, "จำนวนที่เลือกเกินสต็อกที่มี")
        return redirect('store_list')

    # ตรวจสอบว่ามีร้านอื่นในตะกร้าหรือไม่
    cart_item = Cart.objects.filter(user=request.user).first()
    if cart_item and str(cart_item.store.id) != store_id:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'message': 'คุณต้องล้างตะกร้าก่อนเพิ่มสินค้าจากร้านใหม่',
            })
        messages.error(request, "คุณต้องล้างตะกร้าก่อนเพิ่มสินค้าจากร้านใหม่")
        return redirect('cart')

    if quantity > 0:
        cart_item, created = Cart.objects.get_or_create(
            user=request.user,
            store=store,
            defaults={'quantity': quantity, 'note': note}
        )
        if not created:
            cart_item.quantity = quantity
            cart_item.note = note
            cart_item.save()
        message = f"เพิ่ม {store.name} ลงตะกร้าเรียบร้อย!"
    else:
        Cart.objects.filter(user=request.user, store=store).delete()
        message = f"ลบ {store.name} ออกจากตะกร้าเรียบร้อย!"

    cart_items = Cart.objects.filter(user=request.user)
    cart_count = sum(item.quantity for item in cart_items)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'message': message,
            'cart_count': cart_count
        })
    messages.success(request, message)
    return redirect('store_list')

@login_required(login_url='login')
def cart(request):
    if not request.user.is_authenticated:
        messages.warning(request, "กรุณาล็อกอินเพื่อดูตะกร้าสินค้า")
        return redirect('login')

    cart_items = Cart.objects.filter(user=request.user).select_related('store')
    user_allergies = Allergy.objects.filter(user=request.user).values_list('name', flat=True)
    total_price = sum(item.total_discounted_price for item in cart_items)
    shipping_fee = 9.0
    total_with_shipping = total_price + shipping_fee
    addresses = Address.objects.filter(user=request.user)

    for item in cart_items:
        item.allergens = item.store.allergen_ingredients.split(',') if item.store.allergen_ingredients else []
        # ตรวจสอบว่ามีสารก่อภูมิแพ้ที่ตรงกับของผู้ใช้หรือไม่
        item.has_allergy_warning = False
        if item.allergens:
            allergens_list = [allergen.strip() for allergen in item.allergens if allergen.strip()]
            item.has_allergy_warning = any(allergen.lower() in [ua.lower() for ua in user_allergies] for allergen in allergens_list)

    if request.method == 'POST':
        if request.POST.get('clear_cart'):
            cart_items.delete()
            messages.success(request, "ตะกร้าถูกล้างเรียบร้อยแล้ว")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': 'ตะกร้าถูกล้างเรียบร้อยแล้ว'})
            return redirect('cart')

        store_id = request.POST.get('store_id')
        note = request.POST.get('note', '')
        try:
            quantity = int(request.POST.get('quantity', 0))
            store = get_object_or_404(Store, id=store_id)
            if store.quantity_available is not None and quantity > store.quantity_available:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': 'จำนวนที่เลือกเกินสต็อกที่มี'})
                messages.error(request, "จำนวนที่เลือกเกินสต็อกที่มี")
                return redirect('cart')
            # ตรวจสอบร้านในตะกร้า
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
            messages.success(request, message)
        except (ValueError, Store.DoesNotExist) as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': f'คำขอไม่ถูกต้อง: {str(e)}'})
            messages.error(request, f"คำขอไม่ถูกต้อง: {str(e)}")

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': message})
        return redirect('cart')

    context = {
        'cart_items': cart_items,
        'total_price': total_price,
        'shipping_fee': shipping_fee,
        'total_with_shipping': total_with_shipping,
        'addresses': addresses,
    }
    return render(request, 'cart.html', context)

@login_required(login_url='login')
def checkout(request):
    if not request.user.is_authenticated:
        messages.warning(request, "กรุณาล็อกอินเพื่อดำเนินการชำระเงิน")
        return redirect('login')

    cart_items = Cart.objects.filter(user=request.user)
    total_price = sum(item.total_discounted_price or 0 for item in cart_items)
    shipping_fee = 9.0
    total_with_shipping = total_price + shipping_fee

    if not cart_items:
        messages.warning(request, "ตะกร้าของคุณว่างเปล่า กรุณาเพิ่มสินค้าก่อนดำเนินการชำระเงิน")
        return redirect('store_list')

    addresses = Address.objects.filter(user=request.user)

    if request.method == 'POST':
        address_id = request.POST.get('address_id')
        payment_method = request.POST.get('payment_method')

        if not address_id or not payment_method:
            messages.error(request, "กรุณาเลือกที่อยู่จัดส่งและช่องทางชำระเงิน")
            return render(request, 'cart.html', {
                'cart_items': cart_items,
                'total_price': total_price,
                'shipping_fee': shipping_fee,
                'total_with_shipping': total_with_shipping,
                'addresses': addresses,
            })

        try:
            delivery_address = Address.objects.get(id=address_id, user=request.user)
        except Address.DoesNotExist:
            messages.error(request, "ที่อยู่จัดส่งไม่ถูกต้อง")
            return render(request, 'cart.html', {
                'cart_items': cart_items,
                'total_price': total_price,
                'shipping_fee': shipping_fee,
                'total_with_shipping': total_with_shipping,
                'addresses': addresses,
            })

        order = Order.objects.create(
            buyer=request.user,
            delivery_address=delivery_address,
            total_price=total_price,
            shipping_fee=shipping_fee,
            total_with_shipping=total_with_shipping,
            payment_method=payment_method,
        )

        for item in cart_items:
            OrderItem.objects.create(
                order=order,
                store=item.store,
                quantity=item.quantity,
                price=item.store.discounted_price,
                note=item.note,
            )

        cart_items.delete()
        messages.success(request, f"สั่งซื้อสำเร็จ! หมายเลขคำสั่งซื้อ: {order.id}")
        return render(request, 'checkout_success.html', {'order': order})

    return render(request, 'cart.html', {
        'cart_items': cart_items,
        'total_price': total_price,
        'shipping_fee': shipping_fee,
        'total_with_shipping': total_with_shipping,
        'addresses': addresses,
    })

@login_required
def profile_settings(request):
    # ตรวจสอบหรือสร้าง Profile ถ้ายังไม่มี
    profile, created = Profile.objects.get_or_create(user=request.user)
    
    addresses = Address.objects.filter(user=request.user)
    allergies = Allergy.objects.filter(user=request.user)

    if request.method == 'POST':
        form_type = request.POST.get('form_type')

        if form_type == 'profile':
            form = ProfileForm(request.POST, instance=profile, user=request.user)
            if form.is_valid():
                form.save()
                messages.success(request, 'อัปเดตข้อมูลส่วนตัวเรียบร้อยแล้ว')
                return redirect('profile_settings')
            else:
                messages.error(request, 'เกิดข้อผิดพลาดในการอัปเดตข้อมูลส่วนตัว กรุณาตรวจสอบข้อมูล')

        elif form_type == 'address':
            form = AddressForm(request.POST)
            if form.is_valid():
                address = form.save(commit=False)
                address.user = request.user
                address.save()
                messages.success(request, 'เพิ่มที่อยู่เรียบร้อยแล้ว')
                return redirect('profile_settings')
            else:
                messages.error(request, 'เกิดข้อผิดพลาดในการเพิ่มที่อยู่ กรุณาตรวจสอบข้อมูล')

        elif form_type == 'allergy':
            form = AllergyForm(request.POST)
            if form.is_valid():
                allergy = form.save(commit=False)
                allergy.user = request.user
                allergy.save()
                messages.success(request, 'เพิ่มสารก่อภูมิแพ้เรียบร้อยแล้ว')
                return redirect('profile_settings')
            else:
                messages.error(request, 'เกิดข้อผิดพลาดในการเพิ่มสารก่อภูมิแพ้ กรุณาตรวจสอบข้อมูล')

        elif form_type == 'delete_address':
            address_id = request.POST.get('address_id')
            try:
                address = Address.objects.get(id=address_id, user=request.user)
                address.delete()
                messages.success(request, 'ลบที่อยู่เรียบร้อยแล้ว')
            except Address.DoesNotExist:
                messages.error(request, 'ไม่พบที่อยู่ที่ต้องการลบ')
            return redirect('profile_settings')

        elif form_type == 'delete_allergy':
            allergy_id = request.POST.get('allergy_id')
            try:
                allergy = Allergy.objects.get(id=allergy_id, user=request.user)
                allergy.delete()
                messages.success(request, 'ลบสารก่อภูมิแพ้เรียบร้อยแล้ว')
            except Allergy.DoesNotExist:
                messages.error(request, 'ไม่พบสารก่อภูมิแพ้ที่ต้องการลบ')
            return redirect('profile_settings')

    address_form = AddressForm()
    allergy_form = AllergyForm()
    profile_form = ProfileForm(instance=profile, user=request.user)

    context = {
        'profile': profile,
        'addresses': addresses,
        'allergies': allergies,
        'address_form': address_form,
        'allergy_form': allergy_form,
        'profile_form': profile_form,
    }
    return render(request, 'profile_settings.html', context)