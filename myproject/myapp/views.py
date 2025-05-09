from django.shortcuts import render
from .models import Store, Cart
from django.utils import timezone
from django.views.generic import ListView
from django.views.generic import DetailView
from django.shortcuts import redirect
from django.contrib import messages

def home(request):
    # Get 3 active stores, prioritizing surprise boxes
    featured_stores = Store.objects.filter(
        is_active=True,
        available_from__lte=timezone.now(),
        available_until__gte=timezone.now()
    ).order_by('-is_surprise_box')[:3]
    
    context = {
        'featured_stores': featured_stores,
    }
    return render(request, 'home.html', context)

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
        if self.request.GET.get('surprise_box'):
            queryset = queryset.filter(is_surprise_box=True)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['surprise_box_filter'] = self.request.GET.get('surprise_box', '')
        return context
    
class StoreDetailView(DetailView):
    model = Store
    template_name = 'store_detail.html'
    context_object_name = 'store'

    def post(self, request, *args, **kwargs):
        store = self.get_object()
        if not request.user.is_authenticated:
            messages.error(request, "Please log in to add items to your cart.")
            return redirect('login')
        
        quantity = int(request.POST.get('quantity', 1))
        if quantity > store.quantity_available:
            messages.error(request, "Requested quantity exceeds available stock.")
            return redirect('store_detail', pk=store.id)
        
        cart_item, created = Cart.objects.get_or_create(
            user=request.user,
            store=store,
            defaults={'quantity': quantity}
        )
        if not created:
            cart_item.quantity += quantity
            cart_item.save()
        
        messages.success(request, f"{store.name} added to your cart!")
        return redirect('store_detail', pk=store.id)
    
def cart_view(request):
    cart_items = Cart.objects.filter(user=request.user) if request.user.is_authenticated else []
    context = {'cart_items': cart_items}
    return render(request, 'cart.html', context)