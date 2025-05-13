from django.urls import path
from . import views
from django.contrib.auth.views import LogoutView
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('', views.home, name='home'),
    path('stores/', views.StoreListView.as_view(), name='store_list'),
    path('stores/<uuid:pk>/', views.StoreDetailView.as_view(), name='store_detail'),
    path('cart/add/', views.add_to_cart, name='add_to_cart'),
    path('cart/', views.cart, name='cart'),
    path('checkout/', views.checkout, name='checkout'),
    path('login/', auth_views.LoginView.as_view(template_name='account/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    # ถ้ามี signup view ใน views.py
    path('signup/', views.signup, name='signup'),
    path('profile/settings/', views.profile_settings, name='profile_settings'),
    path('orders/', views.order_history, name='order_history'),
    path('checkout/success/<uuid:order_id>/', views.checkout_success, name='checkout_success'),
    path('order/delete/<uuid:order_id>/', views.delete_order, name='delete_order'),
    path('order/update_status/<int:order_id>/', views.update_order_status, name='update_order_status'),
    path('review/submit/', views.submit_review, name='submit_review'),
]