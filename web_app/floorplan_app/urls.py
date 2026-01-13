from django.urls import path
from . import views

urlpatterns = [
    path("", views.homepage, name="homepage"),
    path("homepage.html", views.homepage, name="homepage_html"),
    path("index/", views.index, name="index"),
    path("survey/", views.survey_view, name="survey"),
    
    # --- API ---
    path("api/save-text", views.save_text_request, name="save_text_request"),
    path("api/save-land-settings", views.save_land_settings, name="save_land_settings"),
    path("api/upload-sketch", views.upload_sketch, name="upload_sketch"),
    path("api/latest-land-info", views.latest_land_info, name="latest_land_info"),
    path("api/job-status/<str:job_id>", views.job_status, name="job_status"),
    path("api/survey/", views.survey_view, name="survey_api"),
    
    # API Duy nhất cho Interactive Editor (Xử lý cả lưu Full Layout và lưu Image Only)
    path('api/save-interactive-layout/', views.save_interactive_layout, name='save_interactive_layout'),
]