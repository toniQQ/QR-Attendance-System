from .models import SiteProfile


def site_profile(request):
    return {"profile": SiteProfile.objects.first()}