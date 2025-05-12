from django.urls import path
from .views import home, StoreListView, StoreDetailView, cart_view
from . import views
from django.contrib.auth.views import LogoutView

urlpatterns = [
    path('', home, name='home'),
    path('stores/', StoreListView.as_view(), name='store_list'),
    path('stores/<uuid:pk>/', StoreDetailView.as_view(), name='store_detail'),
    path('cart/', cart_view, name='cart'),
    path('checkout/', views.checkout, name='checkout'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', LogoutView.as_view(next_page='home'), name='logout'),
]