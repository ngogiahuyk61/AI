from django.urls import path
from . import views

urlpatterns = [
    # Trang chủ (Landing Page)
    path("", views.homepage, name="homepage"),
    path("homepage.html", views.homepage, name="homepage_html"),
    
    # Dashboard chính (Sau khi login sẽ vào đây)
    path("floorplan-2D/", views.index, name="dashboard"), 
    path("index/", views.index, name="index"), # Giữ lại để tương thích cũ
    
    # Survey & API
    path("survey/", views.survey_view, name="survey"),
    
    # --- API ---
    path("api/save-text", views.save_text_request, name="save_text_request"),
    path("api/save-land-settings", views.save_land_settings, name="save_land_settings"),
    path("api/upload-sketch", views.upload_sketch, name="upload_sketch"),
    path("api/latest-land-info", views.latest_land_info, name="latest_land_info"),
    path("api/job-status/<str:job_id>", views.job_status, name="job_status"),
    path("api/survey/", views.survey_view, name="survey_api"),
    path('api/save-interactive-layout/', views.save_interactive_layout, name='save_interactive_layout'),
    path('payment/', views.payment_view, name='payment'),
]