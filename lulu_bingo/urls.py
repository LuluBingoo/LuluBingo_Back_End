from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from accounts.views import HealthCheckView

admin.site.site_header = "LuluBingo Admin"
admin.site.site_title = "LuluBingo"
admin.site.index_title = "Welcome to LuluBingo Portal"

urlpatterns = [
    path('admin-ludis/', admin.site.urls),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/games/', include('games.urls')),
    path('api/transactions/', include('transactions.urls')),
    path('api/', include('accounts.urls')),
    path('', HealthCheckView.as_view(), name='health-check'),
]
