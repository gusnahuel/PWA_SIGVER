"""
SIGVER - Distancia entre el técnico y el equipo

La calcula el servidor con PostGIS (no el celular): es la prueba de que la
verificación o el trabajo se hizo en el lugar.
"""
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point

# Mismos umbrales que muestra la PWA al verificar
EN_EL_LUGAR_M = 50
CERCA_M = 300


def punto_gps(latitud, longitud):
    return Point(longitud, latitud, srid=4326)


def distancia_m(queryset, campo, punto):
    """Metros entre `punto` y el campo geográfico del primer objeto del queryset (None si no tiene)."""
    if punto is None:
        return None
    # En columnas "geography" PostGIS mide sobre el elipsoide y devuelve metros
    distancia = (queryset.exclude(**{f'{campo}__isnull': True})
                 .annotate(d=Distance(campo, punto)).values_list('d', flat=True).first())
    return round(distancia.m) if distancia is not None else None


def coincide(metros):
    """Valor de «ubicación coincide» según la distancia: SI / APROXIMADA / NO."""
    if metros <= EN_EL_LUGAR_M:
        return 'SI'
    return 'APROXIMADA' if metros <= CERCA_M else 'NO'


def texto_distancia(metros):
    """'En el lugar (12 m)', 'Cerca (180 m)' o 'Lejos (2,3 km)'."""
    if metros is None:
        return None
    medida = f'{metros} m' if metros < 1000 else f'{metros / 1000:.1f} km'.replace('.', ',')
    return {'SI': 'En el lugar', 'APROXIMADA': 'Cerca', 'NO': 'Lejos'}[coincide(metros)] + f' ({medida})'
