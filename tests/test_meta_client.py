"""
Tests del cliente Meta. Foco actual: normalize_ar_wa_id.

Meta guarda los números argentinos en la whitelist con formato legacy
(54+area+15+local), pero el wa_id que llega en los webhooks usa formato
moderno (54+9+area+local). Sin normalización → error #131030.
"""
from src.whatsapp.meta_client import normalize_ar_wa_id


def test_ar_buenos_aires_basico():
    # wa_id argentino moderno → formato legacy que Meta acepta
    assert normalize_ar_wa_id("5491123456789") == "54111523456789"


def test_ar_buenos_aires_otro_numero():
    assert normalize_ar_wa_id("5491100000000") == "54111500000000"
    assert normalize_ar_wa_id("5491199998888") == "54111599998888"


def test_pass_through_no_argentino():
    # Brasil — no debería tocarse
    assert normalize_ar_wa_id("5511987654321") == "5511987654321"
    # USA
    assert normalize_ar_wa_id("15555555555") == "15555555555"
    # España
    assert normalize_ar_wa_id("34611223344") == "34611223344"


def test_pass_through_ar_area_no_soportada():
    # Mar del Plata (área 223), no manejada aún → passthrough
    assert normalize_ar_wa_id("5492232123456") == "5492232123456"
    # Córdoba (área 351)
    assert normalize_ar_wa_id("5493512123456") == "5493512123456"


def test_pass_through_largo_incorrecto():
    # 549 pero longitud != 13 → passthrough (puede ser fijo, no móvil)
    assert normalize_ar_wa_id("549") == "549"
    assert normalize_ar_wa_id("54911") == "54911"
    assert normalize_ar_wa_id("54911234567890000") == "54911234567890000"


def test_pass_through_vacio_o_none():
    assert normalize_ar_wa_id("") == ""
    assert normalize_ar_wa_id(None) is None
