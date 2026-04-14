from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('api/search/', views.search_api, name='search_api'),
    path('api/save/', views.save_book_api, name='save_api'),
    path('api/delete/', views.delete_book_api, name='delete_api'),
    path('api/rate/', views.rate_book_api, name='rate_api'),
    path('api/library/', views.library_api, name='library_api'),
]
