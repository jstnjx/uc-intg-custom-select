from uc_intg_custom_select.utils import normalize_remote_url, slugify


def test_normalize_remote_url():
    assert normalize_remote_url("192.168.1.20") == "http://192.168.1.20/api/"
    assert normalize_remote_url("http://remote.local/") == "http://remote.local/api/"
    assert normalize_remote_url("https://remote.local/api") == "https://remote.local/api/"


def test_slugify():
    assert slugify("Apple TV Apps") == "apple_tv_apps"
    assert slugify("  TV / Gaming  ") == "tv_gaming"
