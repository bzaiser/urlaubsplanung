from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from pwa import views as pwa_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('pwa/', include('pwa.urls')),
    path('serviceworker.js', pwa_views.service_worker, name='serviceworker'),
    path('manifest.json', pwa_views.manifest, name='manifest'),
    path('', include('travel.urls')),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
