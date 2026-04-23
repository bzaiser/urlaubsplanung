from django.contrib import admin
from django.urls import path, include, re_path
from django.views.static import serve
from django.conf import settings
from django.conf.urls.static import static
from pwa import views as pwa_views

from django.contrib.auth import views as auth_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', auth_views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('pwa/', include('pwa.urls')),
    path('serviceworker_v29.js', pwa_views.service_worker, name='serviceworker'),
    path('manifest.json', pwa_views.manifest, name='manifest'),
    path('', include('travel.urls')),
    
    # Ermöglicht das Laden von Bildern auch wenn DEBUG=False (wichtig für NAS-Betrieb)
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
