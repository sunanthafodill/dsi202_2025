from django.urls import path
from . import views
from django.contrib.auth.views import LoginView, LogoutView

urlpatterns = [
    path('', views.home, name='home'),
    path('stores/', views.StoreListView.as_view(), name='store_list'),
    path('stores/search-suggestions/', views.search_suggestions, name='search_suggestions'),
    path('stores/<uuid:pk>/', views.StoreDetailView.as_view(), name='store_detail'),
    path('cart/add/', views.add_to_cart, name='add_to_cart'),
    path('cart/check/', views.check_cart, name='cart_check'),
    path('cart/', views.cart, name='cart'),
    path('checkout/', views.checkout, name='checkout'),
    path('login/', LoginView.as_view(template_name='account/login.html'), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('signup/', views.signup, name='signup'),
    path('profile/settings/', views.profile_settings, name='profile_settings'),
    path('orders/', views.order_history, name='order_history'),
    path('checkout/success/<uuid:order_id>/', views.checkout_success, name='checkout_success'),
    path('order/delete/<uuid:order_id>/', views.delete_order, name='delete_order'),
    path('order/update_status/<uuid:order_id>/', views.update_order_status, name='update_order_status'),
    path('review/submit/', views.submit_review, name='submit_review'),
    path('address/<uuid:address_id>/', views.get_address, name='get_address'),
    path('api/address/<uuid:address_id>/delete/', views.delete_address, name='delete_address'),
]