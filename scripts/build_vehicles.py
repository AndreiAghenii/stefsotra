"""Build the vehicle tree: make -> model -> year range, 1995 onward.

Two sources, both usable commercially:
  * NHTSA vPIC  -- US Government work, public domain. Broad and reliable, but it only
    knows vehicles sold in the US, so it misses Dacia, Lada and some Skoda/SEAT lines
    that are among the most common cars on Moldovan roads.
  * Wikidata    -- CC0. Fills exactly those gaps.

Scoped to makes actually driven in Moldova rather than all 12,321 vPIC makes, because
a selector listing Koenigsegg and Oshkosh is noise for this shop.

    python3 scripts/build_vehicles.py
"""
import json, os, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), 'data')
UA = {'User-Agent': 'stefsotra-catalog/1.0 (andrei.aghenii@gmail.com)'}
START_YEAR = 1995
THIS_YEAR = 2026

# Makes worth listing for Moldova: EU mainstream, the Soviet/Russian marques still on the
# road, plus the commercial vehicles Stefsotra's hoses actually serve.
MAKES = [
    'Volkswagen', 'Skoda', 'Renault', 'Dacia', 'Opel', 'Ford', 'Peugeot', 'Citroen',
    'Mercedes-Benz', 'BMW', 'Audi', 'Seat', 'Fiat', 'Toyota', 'Nissan', 'Honda',
    'Hyundai', 'Kia', 'Mazda', 'Mitsubishi', 'Suzuki', 'Subaru', 'Volvo', 'Saab',
    'Chevrolet', 'Chrysler', 'Jeep', 'Dodge', 'Land Rover', 'Jaguar', 'Mini',
    'Alfa Romeo', 'Lancia', 'Porsche', 'Smart', 'Ssangyong', 'Daewoo', 'Daihatsu',
    'Lada', 'UAZ', 'GAZ', 'KAMAZ', 'MAZ', 'ZAZ', 'Moskvich',
    'Iveco', 'MAN', 'Scania', 'DAF', 'Setra', 'Neoplan',
]
# vPIC has no useful record for these; Wikidata carries them.
WIKIDATA_ONLY = {'Dacia', 'Lada', 'UAZ', 'GAZ', 'KAMAZ', 'MAZ', 'ZAZ', 'Moskvich',
                 'Skoda', 'Seat', 'Setra', 'Neoplan'}

# Neither source covers the Soviet/CIS marques or the truck ranges properly, yet these
# are exactly the vehicles Stefsotra's KAMAZ and MAZ hoses are sold for. Curated by hand
# from the manufacturers' own model designations.
SUPPLEMENT = {
    'KAMAZ': ['4308', '4310', '43118', '43253', '5320', '53205', '53212', '53215',
              '5350', '53605', '5410', '54115', '5460', '5490', '55111', '6350',
              '6460', '6520', '65115', '65116', '65117', '65201', '6540'],
    'MAZ':   ['4370', '5336', '5337', '5340', '5432', '5440', '5516', '5551', '6303',
              '6312', '6430', '6501', '543205', '551605'],
    'Lada':  ['2101', '2104', '2105', '2106', '2107', '2108', '2109', '21099',
              '2110', '2111', '2112', '2113', '2114', '2115', '4x4 (Niva)',
              'Niva Travel', 'Kalina', 'Priora', 'Granta', 'Vesta', 'XRAY', 'Largus'],
    'Moskvich': ['2140', '2141', 'Aleko', 'Svyatogor', 'Yuri Dolgoruky', '3', '6'],
    'Ssangyong': ['Actyon', 'Korando', 'Kyron', 'Musso', 'Rexton', 'Rodius', 'Tivoli',
                  'XLV'],
    'Setra':  ['S 315', 'S 415', 'S 416', 'S 417', 'S 431', 'S 515', 'S 516', 'S 517'],
    'UAZ':    ['Hunter', 'Patriot', 'Pickup', 'Profi', '3151', '3303', '3909', '452'],
    'GAZ':    ['Gazelle', 'Gazelle Next', 'Gazon Next', 'Sobol', 'Valdai', '3307',
               '3309', '3110', '31105', '2705', '3302'],
    # Wikidata labels this brand "Skoda Auto" with a caron, so the plain-ASCII lookup
    # returned nothing. Supplemented directly -- it is far too common in Moldova to ship
    # an empty model list for.
    # Wikidata capitalises this brand "SEAT"; the mixed-case lookup found nothing.
    'Seat': ['Alhambra', 'Altea', 'Arona', 'Arosa', 'Ateca', 'Cordoba', 'Exeo', 'Ibiza',
             'Inca', 'Leon', 'Marbella', 'Mii', 'Tarraco', 'Toledo'],
    'Skoda': ['Favorit', 'Felicia', 'Forman', 'Octavia', 'Fabia', 'Superb', 'Roomster',
              'Yeti', 'Rapid', 'Citigo', 'Karoq', 'Kodiaq', 'Scala', 'Kamiq', 'Enyaq',
              'Praktik'],
}
# MAN's vPIC record is thousands of chassis codes rather than model families; keep the
# families a customer would recognise.
MAN_FAMILIES = ['TGA', 'TGL', 'TGM', 'TGS', 'TGX', 'TGE', 'L2000', 'M2000', 'F2000',
                'Lion\'s Coach', 'Lion\'s City']


def get(url, timeout=60):
    return json.loads(urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=timeout).read().decode('utf-8'))


def vpic_models(make):
    """Model names per year, collapsed into first/last-seen year ranges."""
    seen = {}
    for year in range(START_YEAR, THIS_YEAR + 1):
        url = ('https://vpic.nhtsa.dot.gov/api/vehicles/getmodelsformakeyear/make/'
               f'{urllib.parse.quote(make.lower())}/modelyear/{year}?format=json')
        try:
            d = get(url, timeout=40)
        except Exception:
            continue
        for r in d.get('Results') or []:
            n = (r.get('Model_Name') or '').strip()
            if not n:
                continue
            if n in seen:
                seen[n][1] = year
            else:
                seen[n] = [year, year]
        time.sleep(0.05)
    return seen


WD_QUERY = """
SELECT ?modelLabel ?start ?end WHERE {
  ?brand rdfs:label "%s"@en .
  ?model wdt:P176 ?brand .
  ?model wdt:P31/wdt:P279* wd:Q3231690 .
  OPTIONAL { ?model wdt:P571 ?start_ }
  OPTIONAL { ?model wdt:P730 ?end_ }
  BIND(YEAR(?start_) AS ?start) BIND(YEAR(?end_) AS ?end)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" }
} LIMIT 400
"""


def wikidata_models(make):
    q = WD_QUERY % make.replace('"', '')
    url = 'https://query.wikidata.org/sparql?' + urllib.parse.urlencode(
        {'query': q, 'format': 'json'})
    try:
        d = get(url, timeout=90)
    except Exception as e:
        print(f"    wikidata failed for {make}: {str(e)[:60]}")
        return {}
    seen = {}
    for b in d['results']['bindings']:
        name = b['modelLabel']['value'].strip()
        if not name or name.startswith('Q'):
            continue
        s = int(b['start']['value']) if 'start' in b else None
        e = int(b['end']['value']) if 'end' in b else None
        lo = max(s or START_YEAR, START_YEAR)
        hi = min(e or THIS_YEAR, THIS_YEAR)
        if hi < START_YEAR:
            continue
        if name in seen:
            seen[name] = [min(seen[name][0], lo), max(seen[name][1], hi)]
        else:
            seen[name] = [lo, hi]
    return seen


def main():
    makes = {}
    for i, make in enumerate(MAKES, 1):
        models = {}
        if make not in WIKIDATA_ONLY:
            models = vpic_models(make)
        if len(models) < 3:                       # thin or absent -> try Wikidata
            wd = wikidata_models({'Skoda': 'Škoda Auto', 'Seat': 'SEAT'}.get(make, make))
            for k, v in wd.items():
                models.setdefault(k, v)
        if make == 'MAN':                         # drop the chassis-code noise
            models = {n: y for n, y in models.items()
                      if any(n.upper().startswith(f.upper()) for f in MAN_FAMILIES)}
            for f in MAN_FAMILIES:
                models.setdefault(f, [START_YEAR, THIS_YEAR])
        for name in SUPPLEMENT.get(make, []):     # hand-curated, wins on absence only
            models.setdefault(name, [START_YEAR, THIS_YEAR])
        if not models:
            print(f"  [{i:>2}/{len(MAKES)}] {make:<16} no data, skipped")
            continue
        makes[make] = sorted(
            ({'name': n, 'from': y[0], 'to': y[1]} for n, y in models.items()),
            key=lambda m: m['name'])
        print(f"  [{i:>2}/{len(MAKES)}] {make:<16} {len(models)} models")

    out = {'start_year': START_YEAR, 'end_year': THIS_YEAR,
           'sources': ['NHTSA vPIC (public domain)', 'Wikidata (CC0)'],
           'makes': makes}
    os.makedirs(DATA, exist_ok=True)
    path = os.path.join(DATA, 'vehicles.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    total = sum(len(v) for v in makes.values())
    print(f"\n{len(makes)} makes, {total} models -> {os.path.getsize(path)/1024:.0f} KB")


if __name__ == '__main__':
    main()
