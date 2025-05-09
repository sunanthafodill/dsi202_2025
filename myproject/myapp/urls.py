from django.urls import path
from .views import home, StoreListView, StoreDetailView, cart_view

urlpatterns = [
    path('', home, name='home'),
    path('stores/', StoreListView.as_view(), name='store_list'),
    path('stores/<uuid:pk>/', StoreDetailView.as_view(), name='store_detail'),
    path('cart/', cart_view, name='cart'),
]