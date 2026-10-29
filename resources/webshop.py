"""Validation shared by the webshop endpoints (no database or UI dependencies)."""
from uuid import UUID


def validate_webshop_product(product, variants, attributes):
    if not str(product.get('name', '')).strip():
        raise ValueError('A terméknév kötelező.')
    if not 1 <= len(variants) <= 100:
        raise ValueError('A termékhez 1–100 rendelhető változat szükséges.')
    skus, ids = set(), set()
    for variant in variants:
        for key in ('sku', 'size', 'type'):
            if not str(variant.get(key, '')).strip():
                raise ValueError('Minden változatnál cikkszám, méret és típus szükséges.')
        sku = variant['sku'].strip().casefold()
        if sku in skus:
            raise ValueError('A változatok cikkszáma legyen egyedi.')
        skus.add(sku)
        if variant.get('id'):
            vid = str(UUID(str(variant['id'])))
            if vid in ids:
                raise ValueError('Ismétlődő változatazonosító.')
            ids.add(vid)
        price = variant.get('price_huf')
        if type(price) is not int or not 0 <= price <= 10_000_000:
            raise ValueError('Az ár 0 és 10 000 000 Ft közötti egész szám legyen.')
        values = variant.get('attributes') or {}
        allowed = {a['name']: a for a in attributes}
        if any(name not in allowed for name in values):
            raise ValueError('Ismeretlen terméktulajdonság.')
        for name, definition in allowed.items():
            value = values.get(name, '')
            if definition.get('required') and not value:
                raise ValueError(f'Kötelező tulajdonság: {name}.')
            if value and value not in definition.get('values', []):
                raise ValueError(f'Nem választható érték: {name}.')


def validate_webshop_items(items):
    if not 1 <= len(items) <= 50:
        raise ValueError('A kosár 1–50 tételt tartalmazhat.')
    seen = set()
    for item in items:
        identifier = str(UUID(str(item['variant_id'])))
        if identifier in seen:
            raise ValueError('Ismétlődő kosártétel.')
        seen.add(identifier)
        if type(item['quantity']) is not int or not 1 <= item['quantity'] <= 99:
            raise ValueError('A darabszám 1 és 99 közötti egész szám legyen.')
