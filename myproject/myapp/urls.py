from django.urls import path
from . import views
from django.contrib.auth.views import LogoutView

urlpatterns = [
    path('', views.home, name='home'),
    path('stores/', views.StoreListView.as_view(), name='store_list'),
    path('stores/<uuid:pk>/', views.StoreDetailView.as_view(), name='store_detail'),
    path('cart/', views.cart, name='cart'),
    path('checkout/', views.checkout, name='checkout'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', LogoutView.as_view(next_page='home'), name='logout'),
    path('cart/add/', views.add_to_cart, name='add_to_cart'),
]