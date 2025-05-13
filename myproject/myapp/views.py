from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import ListView, DetailView
from django.http import JsonResponse
from django.contrib import messages
from django.db.models import Q
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from .models import Store, Cart
from datetime import datetime

def home(request):
    context = {
        'welcome_message': "ยินดีต้อนรับสู่ IMSUK",
        'mission_statement': "เรามุ่งมั่นลดขยะอาหารและต่อสู้กับภาวะโลกร้อนด้วยความเห็นอกเห็นใจต่อโลก ผู้คน และร้านอาหาร"
    }
    return render(request, 'home.html', context)

class StoreListView(ListView):
    model = Store
    template_name = 'store_list.html'
    context_object_name = 'stores'
    paginate_by = 9

    def get_queryset(self):
        queryset = Store.objects.filter(is_active=True)
        # Compare available_from and available_until with current time in Thailand
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
        # Get cart quantity for the store
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

    if quantity > 0:
        cart_item, created = Cart.objects.get_or_create(
            user=request.user,
            store=store,
            defaults={'quantity': quantity}
        )
        if not created:
            cart_item.quantity = quantity  # Update quantity
            cart_item.save()
        message = f"เพิ่ม {store.name} ลงตะกร้าเรียบร้อย!"
    else:
        Cart.objects.filter(user=request.user, store=store).delete()
        message = f"ลบ {store.name} ออกจากตะกร้าเรียบร้อย!"

    # Calculate cart count
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

def base_context(request):
    cart_count = 0
    if request.user.is_authenticated:
        cart_items = Cart.objects.filter(user=request.user)
        cart_count = sum(item.quantity for item in cart_items)
    return {
        'cart_count': cart_count,
        'is_authenticated': request.user.is_authenticated,
    }

def cart(request):
    if not request.user.is_authenticated:
        messages.warning(request, "กรุณาล็อกอินเพื่อดูตะกร้าสินค้า")
        return redirect('login')
    
    cart_items = Cart.objects.filter(user=request.user)
    total_price = sum(item.total_discounted_price or 0 for item in cart_items)
    
    for item in cart_items:
        item.allergens = item.store.allergen_ingredients.split(',') if item.store.allergen_ingredients else []
    
    if request.method == 'POST':
        if request.POST.get('clear_cart'):
            cart_items.delete()
            messages.success(request, "ตะกร้าถูกล้างเรียบร้อยแล้ว")
        else:
            store_id = request.POST.get('store_id')
            try:
                quantity = int(request.POST.get('quantity', 0))
                store = get_object_or_404(Store, id=store_id)
                if store.quantity_available is not None and quantity > store.quantity_available:
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'success': False, 'message': 'จำนวนที่เลือกเกินสต็อกที่มี'})
                    messages.error(request, "จำนวนที่เลือกเกินสต็อกที่มี")
                    return redirect('cart')
                cart_item, created = Cart.objects.get_or_create(
                    user=request.user,
                    store=store,
                    defaults={'quantity': quantity}
                )
                if not created:
                    if quantity <= 0:
                        cart_item.delete()
                        messages.success(request, f"ลบ {store.name} ออกจากตะกร้าเรียบร้อย")
                    else:
                        cart_item.quantity = quantity
                        cart_item.save()
                        messages.success(request, f"อัปเดตจำนวน {store.name} เรียบร้อย")
                else:
                    messages.success(request, f"เพิ่ม {store.name} ลงตะกร้าเรียบร้อย")
            except (ValueError, Store.DoesNotExist) as e:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': f'คำขอไม่ถูกต้อง: {str(e)}'})
                messages.error(request, f"คำขอไม่ถูกต้อง: {str(e)}")
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': list(messages.get_messages(request))[-1].message})
        return redirect('cart')
    
    return render(request, 'cart.html', {
        'cart_items': cart_items,
        'total_price': total_price
    })

def checkout(request):
    if not request.user.is_authenticated:
        messages.warning(request, "กรุณาล็อกอินเพื่อดำเนินการชำระเงิน")
        return redirect('login')
    
    cart_items = Cart.objects.filter(user=request.user)
    total_price = sum(item.total_discounted_price or 0 for item in cart_items)
    
    if not cart_items:
        messages.warning(request, "ตะกร้าของคุณว่างเปล่า กรุณาเพิ่มสินค้าก่อนดำเนินการชำระเงิน")
        return redirect('store_list')
    
    return render(request, 'checkout.html', {
        'cart_items': cart_items,
        'total_price': total_price
    })