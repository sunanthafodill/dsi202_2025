from django.shortcuts import render, get_object_or_404, redirect
from .models import Store, Cart
from django.utils import timezone
from django.views.generic import ListView
from django.views.generic import DetailView
from django.shortcuts import redirect
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User

def home(request):
    context = {
        'welcome_message': "ยินดีต้อนรับสู่ IMSUK",
        'mission_statement': "เรามุ่งมั่นลดขยะอาหารและต่อสู้กับภาวะโลกร้อนด้วยความเห็นอกเห็นใจต่อโลก ผู้คน และร้านอาหาร"
    }
    return render(request, 'home.html', context)

def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, "ล็อกอินสำเร็จ!")
            next_url = request.POST.get('next', 'home')
            return redirect(next_url)
        else:
            messages.error(request, "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    
    return render(request, 'login.html', {'next': request.GET.get('next', '')})

def register_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')
        
        if User.objects.filter(username=username).exists():
            messages.error(request, "ชื่อผู้ใช้นี้มีอยู่แล้ว")
        elif User.objects.filter(email=email).exists():
            messages.error(request, "อีเมลนี้มีอยู่แล้ว")
        elif password1 != password2:
            messages.error(request, "รหัสผ่านไม่ตรงกัน")
        else:
            user = User.objects.create_user(username=username, email=email, password=password1)
            user.save()
            login(request, user)
            messages.success(request, "สมัครสมาชิกสำเร็จ! ยินดีต้อนรับ")
            return redirect('home')
    
    return render(request, 'register.html')

class StoreListView(ListView):
    model = Store
    template_name = 'store_list.html'
    context_object_name = 'stores'
    paginate_by = 9

    def get_queryset(self):
        queryset = Store.objects.filter(
            is_active=True,
            available_from__lte=timezone.now(),
            available_until__gte=timezone.now()
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
        return context

    def post(self, request, *args, **kwargs):
        session_key = request.session.session_key or request.session.create()
        store_id = request.POST.get('store_id')
        quantity = int(request.POST.get('quantity', 1))
        
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
                session_key=session_key,
                store=store,
                defaults={'quantity': quantity, 'user': request.user if request.user.is_authenticated else None}
            )
            if not created:
                cart_item.quantity += quantity
                cart_item.save()
            message = f"เพิ่ม {store.name} ลงตะกร้าเรียบร้อย!"
        else:
            Cart.objects.filter(session_key=session_key, store=store).delete()
            message = f"ลบ {store.name} ออกจากตะกร้าเรียบร้อย!"

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': message})
        messages.success(request, message)
        return redirect('store_list')
    
def base_context(request):
    if not request.session.session_key:
        request.session.create()
    session_key = request.session.session_key
    cart_items = Cart.objects.filter(session_key=session_key)
    cart_count = sum(item.quantity for item in cart_items)
    return {
        'cart_count': cart_count,
        'is_authenticated': request.user.is_authenticated,
    }

class StoreDetailView(DetailView):
    model = Store
    template_name = 'store_detail.html'
    context_object_name = 'store'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # ไม่ split additional_images เพราะเป็น list จาก JSONField
        context['store'].additional_images = self.object.additional_images or []
        context.update(base_context(self.request))
        return context

    def post(self, request, *args, **kwargs):
        if not request.session.session_key:
            request.session.create()
        session_key = request.session.session_key
        store = self.get_object()
        try:
            quantity = int(request.POST.get('quantity', 1))
        except ValueError:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': 'จำนวนไม่ถูกต้อง'})
            messages.error(request, "จำนวนไม่ถูกต้อง")
            return redirect('store_detail', pk=store.id)

        if quantity < 0:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': 'จำนวนต้องไม่น้อยกว่า 0'})
            messages.error(request, "จำนวนต้องไม่น้อยกว่า 0")
            return redirect('store_detail', pk=store.id)
        if store.quantity_available is not None and quantity > store.quantity_available:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': 'จำนวนที่เลือกเกินสต็อกที่มี'})
            messages.error(request, "จำนวนที่เลือกเกินสต็อกที่มี")
            return redirect('store_detail', pk=store.id)
        
        if quantity > 0:
            cart_item, created = Cart.objects.get_or_create(
                session_key=session_key,
                store=store,
                defaults={'quantity': quantity, 'user': request.user if request.user.is_authenticated else None}
            )
            if not created:
                cart_item.quantity = quantity
                cart_item.save()
            message = f"เพิ่ม {store.name} ลงตะกร้าเรียบร้อย!"
        else:
            Cart.objects.filter(session_key=session_key, store=store).delete()
            message = f"ลบ {store.name} ออกจากตะกร้าเรียบร้อย!"
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': message})
        messages.success(request, message)
        return redirect('store_detail', pk=store.id)

def cart(request):
    session_key = request.session.session_key or request.session.create()
    cart_items = Cart.objects.filter(session_key=session_key)
    total_price = sum(item.total_discounted_price or 0 for item in cart_items)
    
    print('Cart items:', list(cart_items.values('store__name', 'quantity', 'total_discounted_price')))
    print('Total price:', total_price)
    
    for item in cart_items:
        item.allergens = item.store.allergen_ingredients.split(',') if item.store.allergen_ingredients else []
    
    if request.method == 'POST':
        print('POST data:', request.POST)
        if request.POST.get('clear_cart'):
            cart_items.delete()
            messages.success(request, "Cart cleared.")
        else:
            store_id = request.POST.get('store_id')
            try:
                quantity = int(request.POST.get('quantity', 0))
                store = get_object_or_404(Store, id=store_id)
                if store.quantity_available is not None and quantity > store.quantity_available:
                    return JsonResponse({'success': False, 'message': 'จำนวนที่เลือกเกินสต็อกที่มี'})
                cart_item, created = Cart.objects.get_or_create(
                    session_key=session_key,
                    store=store,
                    defaults={'quantity': quantity, 'user': request.user if request.user.is_authenticated else None}
                )
                if not created:
                    if quantity <= 0:
                        cart_item.delete()
                        messages.success(request, f"{store.name} removed from cart.")
                    else:
                        cart_item.quantity = quantity
                        cart_item.save()
                        messages.success(request, f"{store.name} quantity updated.")
                else:
                    messages.success(request, f"{store.name} added to cart.")
            except (ValueError, Store.DoesNotExist) as e:
                print('Error:', str(e))
                return JsonResponse({'success': False, 'message': f'Invalid request: {str(e)}'})
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': messages.get_messages(request).last().message})
        return redirect('cart')
    
    return render(request, 'cart.html', {
        'cart_items': cart_items,
        'total_price': total_price
    })

def checkout(request):
    session_key = request.session.session_key or request.session.create()
    cart_items = Cart.objects.filter(session_key=session_key)
    total_price = sum(item.total_discounted_price or 0 for item in cart_items)
    
    if not cart_items:
        messages.warning(request, "Your cart is empty. Add items to proceed to checkout.")
        return redirect('store_list')
    
    return render(request, 'checkout.html', {
        'cart_items': cart_items,
        'total_price': total_price
    })

def cart_view(request):
    cart_items = Cart.objects.filter(user=request.user) if request.user.is_authenticated else []
    context = {'cart_items': cart_items}
    return render(request, 'cart.html', context)