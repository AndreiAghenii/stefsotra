"""Romanian and Russian product names.

Why this matters more than anything else on the site
----------------------------------------------------
All 114 products are titled in English: "Silicone Hose", "Air Hoses", "Hose Clamps".
A customer in Chișinău searches for *furtun*, *cuplaj*, *colier*. Those words appeared
zero times in our product titles, so no amount of technical SEO would have ranked us for
the query the shop actually lives on. The competitors ranking for "furtun chisinau" have
"Furtunuri" in their page titles; we had "Hose".

How this is done safely
-----------------------
Term-by-term substitution against a hand-written dictionary, longest phrase first.
Numbers, dimensions, angles, part codes, brand names and type letters are never touched:
"Silicone Elbow Hose with Transition 90° L102*102mm" keeps 90°, L102 and 102mm exactly.
Anything the dictionary does not recognise is REPORTED, not guessed at -- a silently
mistranslated technical term is worse than an English one.

Titles that are already Cyrillic keep their Russian form and get a Romanian translation.

    python3 scripts/translate_titles.py          # report only
    python3 scripts/translate_titles.py --write  # write titles into data/products.json
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, 'data')

# Longest phrases first; the substituter applies them in that order so "Hose Clamps"
# wins over "Hose". Keys are matched case-insensitively on whole words.
TERMS = [
    # --- products added from data/extra_products.json. Longest phrases first, so these
    #     resolve before the bare words 'coupling', 'latch' and 'gasket' below.
    ('blind adapter for tw coupling', ('Adaptor orb pentru cuplaj TW', 'Ниппель-заглушка для соединения TW')),
    ('blind cap for tw coupling',   ('Capac orb pentru cuplaj TW', 'Заглушка для соединения TW')),
    ('tw coupling gasket',          ('Garnitură pentru cuplaj TW', 'Прокладка для соединения TW')),
    ('guillemin hose end with latch', ('Racord Guillemin pentru furtun cu clichet',
                                       'Guillemin наконечник для шланга с защёлкой')),
    ('guillemin blind cap with latch', ('Capac orb Guillemin cu clichet', 'Заглушка Guillemin с защёлкой')),
    ('guillemin reducing adapter',  ('Adaptor de reducție Guillemin', 'Редуцирующий переходник Guillemin')),
    ('guillemin female with latch', ('Guillemin mamă cu clichet', 'Guillemin гайка с защёлкой')),
    ('guillemin male without latch', ('Guillemin tată fără clichet', 'Guillemin ниппель без защёлки')),
    ('vb coupling',                 ('Cuplaj VB', 'Соединение VB')),
    ('mb coupling',                 ('Cuplaj MB', 'Соединение MB')),
    ('mk coupling',                 ('Cuplaj MK', 'Соединение MK')),
    ('vk coupling',                 ('Cuplaj VK', 'Соединение VK')),
    ('stainless steel',             ('oțel inoxidabil', 'нержавеющая сталь')),
    ('brass',                       ('alamă', 'латунь')),
    # --- multi-word technical phrases
    ('food-grade technical plate',  ('Placă tehnică alimentară', 'Пластина техническая пищевая')),
    ('rubber sheet (techno-plate)', ('Foaie de cauciuc (tehnoplacă)', 'Резина листовая (технопластина)')),
    ('rubber roll flooring',        ('Covor de cauciuc în rulou', 'Резиновое рулонное покрытие')),
    ('porous sponge rubber',        ('Cauciuc spongios poros', 'Пористая губчатая резина')),
    ('polyurethane aspiration hose', ('Furtun de aspirație din poliuretan', 'Полиуретановый аспирационный рукав')),
    ('food-grade pressure and suction hoses',
                                    ('Furtunuri alimentare de presiune și aspirație',
                                     'Пищевые напорно-всасывающие рукава')),
    ('food-grade suction hoses',    ('Furtunuri alimentare de aspirație', 'Пищевые всасывающие рукава')),
    ('oil and fuel resistant hoses', ('Furtunuri rezistente la ulei și combustibil',
                                      'Маслобензостойкие рукава')),
    ('pvc oil and gasoline resistant hose',
                                    ('Furtun PVC rezistent la ulei și benzină',
                                     'ПВХ рукав маслобензостойкий')),
    ('fuel hose with braided cover', ('Furtun de combustibil cu manta textilă',
                                      'Топливный шланг в оплётке')),
    ('pvc corrugated hose for water', ('Furtun PVC gofrat pentru apă', 'ПВХ гофрированный шланг для воды')),
    ('hoses for sewage trucks',     ('Furtunuri pentru vidanje', 'Рукава для ассенизаторских машин')),
    ('cement discharge hose',       ('Furtun pentru ciment', 'Рукав для подачи цемента')),
    ('aluminum nuts for water pumps', ('Piulițe din aluminiu pentru pompe de apă',
                                       'Алюминиевые гайки для водяных насосов')),
    ('abs plastic hose adapters',   ('Adaptoare de furtun din plastic ABS', 'Адаптеры для шланга из ABS-пластика')),
    ('universal coupling gasket',   ('Garnitură universală pentru cuplaj', 'Универсальная прокладка для соединения')),
    ('guillemin female without latch', ('Guillemin mamă fără clichet', 'Guillemin гайка без защёлки')),
    ('guillemin male with latch',   ('Guillemin tată cu clichet', 'Guillemin ниппель с защёлкой')),
    ('storz coupling with internal thread', ('Cuplaj Storz cu filet interior',
                                             'Соединение Storz с внутренней резьбой')),
    ('storz coupling with tail for hose', ('Cuplaj Storz cu racord pentru furtun',
                                           'Соединение Storz с хвостовиком под шланг')),
    ('storz coupling – female',     ('Cuplaj Storz – mamă', 'Соединение Storz – гайка')),
    ('auto compressor',             ('Compresor auto', 'Автомобильный компрессор')),
    ('truck cargo roof canopy',     ('Prelată pentru camion', 'Тент на кузов грузовика')),
    ('bed liner',                   ('Protecție de benă', 'Вкладыш в кузов')),
    ('polypropylene ball valve',    ('Robinet cu bilă din polipropilenă', 'Шаровой кран из полипропилена')),
    ('ball valve for water',        ('Robinet cu bilă pentru apă', 'Шаровой кран для воды')),
    ('return valve',                ('Supapă de reținere', 'Обратный клапан')),
    ('heavy-duty clamp',            ('Colier de sarcină grea', 'Усиленный хомут')),
    ('hose clamps',                 ('Coliere pentru furtun', 'Хомуты для шланга')),
    ('shaft seals',                 ('Simeringuri', 'Сальники')),
    ('drive belts',                 ('Curele de transmisie', 'Приводные ремни')),
    ('wire fan rakes',              ('Greble evantai din sârmă', 'Веерные грабли проволочные')),
    ('fan lawn rakes',              ('Greble evantai pentru gazon', 'Веерные грабли для газона')),
    ('fan rake',                    ('Greblă evantai', 'Веерные грабли')),
    ('round broom',                 ('Mătură rotundă', 'Метла круглая')),
    ('fregat sprinkler',            ('Aspersor Fregat', 'Дождеватель «Фрегат»')),
    ('nylon tube',                  ('Tub din poliamidă', 'Полиамидная труба')),
    ('rubber cord',                 ('Șnur de cauciuc', 'Резиновый шнур')),
    ('silicone sheet',              ('Foaie de silicon', 'Силиконовая пластина')),
    ('polyurethane sheet',          ('Foaie de poliuretan', 'Полиуретановый лист')),
    ('lay flat hose',               ('Furtun plat', 'Плоскосворачиваемый рукав')),
    ('layflat hose reinforced',     ('Furtun plat armat', 'Плоскосворачиваемый рукав армированный')),
    ('pvc curtains',                ('Perdele din PVC', 'ПВХ завесы')),
    ('pvc pressure hoses',          ('Furtunuri PVC de presiune', 'ПВХ напорные рукава')),
    ('high-pressure hoses',         ('Furtunuri de înaltă presiune', 'Рукава высокого давления')),
    ('ventilation hoses',           ('Furtunuri de ventilație', 'Вентиляционные рукава')),
    ('aluminum ducts',              ('Tuburi din aluminiu', 'Алюминиевые воздуховоды')),
    ('plastering hoses',            ('Furtunuri pentru tencuială', 'Рукава для штукатурки')),
    ('sprayer hose',                ('Furtun pentru stropitoare', 'Шланг для опрыскивателя')),
    ('oxygen hoses',                ('Furtunuri de oxigen', 'Кислородные рукава')),
    ('water hoses',                 ('Furtunuri de apă', 'Водяные шланги')),
    ('air hoses',                   ('Furtunuri de aer', 'Воздушные рукава')),
    ('fire hose',                   ('Furtun de pompieri', 'Пожарный рукав')),
    ('transition hose head',        ('Racord de trecere pentru furtun', 'Переходная головка для шланга')),
    ('guillemin hose end',          ('Racord Guillemin pentru furtun', 'Guillemin наконечник для шланга')),
    ('storz hose end',              ('Racord Storz pentru furtun', 'Storz наконечник для шланга')),
    ('coupling head',               ('Cap de cuplaj', 'Головка соединительная')),
    ('hose head',                   ('Racord de furtun', 'Головка для шланга')),
    ('storz latch',                 ('Clichet Storz', 'Защёлка Storz')),
    ('storz cap',                   ('Capac Storz', 'Заглушка Storz')),
    ('camlock handle',              ('Mâner Camlock', 'Ручка Camlock')),
    # --- silicone family
    ('reinforced silicone damper hose with three rings',
                                    ('Furtun amortizor din silicon armat cu trei inele',
                                     'Армированный силиконовый демпферный шланг с тремя кольцами')),
    ('reinforced silicone hose damper with one ring',
                                    ('Furtun amortizor din silicon armat cu un inel',
                                     'Армированный силиконовый демпферный шланг с одним кольцом')),
    ('silicone hose double damper', ('Furtun amortizor dublu din silicon',
                                     'Силиконовый шланг с двойным демпфером')),
    ('silicone damper hose',        ('Furtun amortizor din silicon', 'Силиконовый демпферный шланг')),
    ('silicone elbow hose with transition', ('Furtun cot din silicon cu reducție',
                                             'Силиконовый патрубок-колено с переходом')),
    ('silicone straight hose with transition', ('Furtun drept din silicon cu reducție',
                                                'Силиконовый прямой патрубок с переходом')),
    ('silicone corrugated hose',    ('Furtun gofrat din silicon', 'Силиконовый гофрированный патрубок')),
    ('silicone u-shaped hose',      ('Furtun din silicon în formă de U', 'Силиконовый патрубок U-образный')),
    ('silicone straight hose',      ('Furtun drept din silicon', 'Силиконовый прямой патрубок')),
    ('silicone elbow hose',         ('Furtun cot din silicon', 'Силиконовый патрубок-колено')),
    ('silicone hoses for',          ('Furtunuri din silicon pentru', 'Силиконовые патрубки для')),
    ('silicone hoses',              ('Furtunuri din silicon', 'Силиконовые патрубки')),
    ('silicone hose',               ('Furtun din silicon', 'Силиконовый патрубок')),
    # --- single words, applied last
    ('camlock reducer',             ('Reducție Camlock', 'Переходник Camlock')),
    ('storz reducer',               ('Reducție Storz', 'Переходник Storz')),
    ('bauer coupling',              ('Cuplaj Bauer', 'Соединение Bauer')),
    ('bauer gasket',                ('Garnitură Bauer', 'Прокладка Bauer')),
    ('camlock gasket',              ('Garnitură Camlock', 'Прокладка Camlock')),
    ('storz gasket',                ('Garnitură Storz', 'Прокладка Storz')),
    ('guillemin gasket',            ('Garnitură Guillemin', 'Прокладка Guillemin')),
    ('camlock type',                ('Camlock tip', 'Camlock тип')),
    ('coupling',                    ('Cuplaj', 'Соединение')),
    ('gasket',                      ('Garnitură', 'Прокладка')),
    ('reducer',                     ('Reducție', 'Переходник')),
    ('hoses',                       ('Furtunuri', 'Рукава')),
    ('hose',                        ('Furtun', 'Шланг')),
    ('tires',                       ('Anvelope', 'Шины')),
    ('caprolon',                    ('Caprolon', 'Капролон')),
    ('paronite',                    ('Paronit', 'Паронит')),
    ('aluminum',                    ('aluminiu', 'алюминий')),
    ('reinforced',                  ('armat', 'армированный')),
    ('cylinder',                    ('cilindri', 'цилиндра')),
    ('latch',                       ('clichet', 'защёлка')),
    ('sheet',                       ('foaie', 'лист')),
]

# "Silicone 45° Elbow Hose" puts the angle in the middle of the phrase, so the phrase
# never matches. Move the angle to the end first, then the ordinary rules apply.
PRE = [(re.compile(r'\b(Silicone)\s+(\d{2,3}\s*°)\s+(Elbow Hose|U-Shaped Hose)', re.I),
        lambda m: '%s %s %s' % (m.group(1), m.group(3), m.group(2)))]

# Cyrillic titles already read correctly in Russian; they need a Romanian version.
CYRILLIC = {
    'ПОЛУРЕТАН В СТЕРЖНЯХ': 'Poliuretan în bare',
    'КАПРАЛОН ГРАФИТОНАПОЛНЕННЫЙ': 'Caprolon grafitat',
    'СИЛИКОНОВЫЙ ШНУР': 'Șnur din silicon',
    'ТЕКСТОЛИТ В ЛИСТАХ': 'Textolit în foi',
    'ПОЛИПРОПИЛЕН ЛИСТОВОЙ': 'Polipropilenă în foi',
}

# Brand names, type letters and codes that must survive untouched.
KEEP = re.compile(r'^(mm|l\d+|pa\d+|nbr|epdm|pmb|abs|pvc|dn\d+|[a-z]{1,2}\d*|'
                  r'toyota|hilux|kenda|klever|bearway|kamaz|maz|mercedes|sprinter|'
                  r'stefsotra|pyatachok|textolith|storz|camlock|guillemin|bauer|'
                  r'vb|mb|mk|vk|type|and|with|for|the|x|no)$', re.I)


def translate(title, idx):
    """Return (translated, unknown_words). idx 0 = Romanian, 1 = Russian."""
    out = title
    for rx, fn in PRE:
        out = rx.sub(fn, out)
    for eng, ro_ru in TERMS:
        out = re.sub(r'(?<![\w-])' + re.escape(eng) + r'(?![\w-])', ro_ru[idx], out, flags=re.I)
    # what is left in Latin letters that we did not translate and did not mean to keep?
    unknown = [w for w in re.findall(r'[A-Za-z][A-Za-z-]{2,}', out)
               if not KEEP.match(w) and w.lower() not in
               {t[1][idx].lower() for t in TERMS} and
               not any(w.lower() in t[1][idx].lower() for t in TERMS)]
    return out.strip(), unknown


def main():
    write = '--write' in sys.argv
    path = os.path.join(DATA, 'products.json')
    cat = json.load(open(path, encoding='utf-8'))

    unknown_all, changed = {}, 0
    for p in cat['products']:
        en = p['title']
        is_cyr = bool(re.search(r'[А-Яа-я]', en))

        if is_cyr:
            ro = en
            for k, v in CYRILLIC.items():
                ro = ro.replace(k, v)
            ro = ro.replace('ММ', 'mm').replace('МM', 'mm')
            ru = en
        else:
            ro, u_ro = translate(en, 0)
            ru, u_ru = translate(en, 1)
            for w in u_ro:
                unknown_all.setdefault(w, []).append(en)

        p['title_ro'] = ro
        p['title_ru'] = ru
        if ro != en:
            changed += 1

    print(f'{changed} of {len(cat["products"])} titles now differ from the English original')
    ro_hits = sum(1 for p in cat['products']
                  if re.search(r'furtun|cuplaj|colier|garnitur|reduc', p['title_ro'], re.I))
    print(f'{ro_hits} Romanian titles contain furtun/cuplaj/colier/garnitură/reducție')

    if unknown_all:
        print(f'\n{len(unknown_all)} word(s) left in English -- check whether they should be:')
        for w, where in sorted(unknown_all.items(), key=lambda x: -len(x[1]))[:20]:
            print(f'   {w:<18} in {len(where)}x  e.g. "{where[0][:52]}"')
    else:
        print('\nno untranslated words outside the keep-list')

    print('\nsamples:')
    for p in cat['products'][:6] + cat['products'][40:44]:
        print(f'   EN {p["title"][:48]:<48}\n   RO {p["title_ro"][:48]:<48}\n   RU {p["title_ru"][:48]}')

    if write:
        json.dump(cat, open(path, 'w', encoding='utf-8'),
                  ensure_ascii=False, separators=(',', ':'))
        print(f'\nwritten to {path}')
    else:
        print('\n(dry run -- pass --write to save)')


if __name__ == '__main__':
    main()
