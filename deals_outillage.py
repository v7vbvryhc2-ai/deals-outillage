import json, re, os, urllib.parse, urllib.request, urllib.error
from datetime import datetime

TOKEN   = os.environ["TELEGRAM_TOKEN"]
CHAT    = os.environ["CHAT_ID"]
SEEN    = "seen_deals.json"
HISTORY = "deals_history.json"

KW_OUTILLAGE = [
    "perceuse","visseuse","meuleuse","scie","ponceuse","marteau","perforateur",
    "tronconneuse","souffleur","compresseur","karcher","nettoyeur haute pression",
    "fer a souder","scie circulaire","scie sauteuse","scie sabre","outil electrique",
    "cloueur","agrafeuse","rabot","affuteuse","polisseuse","decapeur","chalumeau",
    "niveau laser","outillage","parkside","bosch","makita","dewalt","milwaukee",
    "ryobi","einhell","worx","stanley","hikoki","festool","metabo","facom","fabre",
    "aspirateur atelier","visseuse a choc","perceuse visseuse","knipex","gedore",
    "bahco","wera","wiha","irwin","pince","cle a molette","tournevis","maillet",
    "ciseau bois","burin","lime","serre-joint","etau","etabli","coffret outils",
    "caisse outils","boite outils","multimetre","detecteur","disqueuse","meule",
    "fixami","maxoutil","rotopino","discountoffice","idmarket","clickoutils",
    "cdiscount","screwfix","manomano","racetools"
]

KW_JARDINAGE = [
    "tondeuse","robot tondeuse","taille-haie","taille haie","debroussailleuse",
    "scarificateur","aerateur","souffleur feuilles","aspirateur feuilles",
    "tuyau arrosage","arroseur","pompe arrosage","programmateur arrosage",
    "serre","brouette","composteur","broyeur","bache","bordure jardin",
    "motoculteur","motobineuse","elagueur","coupe bordure","rotofil",
    "pulverisateur","traitement jardin","engrais","terreau","pot fleur",
    "jardinage","husqvarna","stihl","greenworks","ego","ferrex","florabest",
    "gardena","kress","outils jardin","beche","fourche","binette","rateau",
    "pelle","transplantoir","secateur","cisaille","echenilloir","griffe",
    "piscine","spa","pompe piscine","robot piscine","liner","bache piscine",
    "parasol","salon jardin","barbecue","plancha","table jardin","chaise jardin",
    "tonte","gazon","pelouse","haie","arbre","arbuste","rosier","plante"
]

KW_ALL = list(set(KW_OUTILLAGE + KW_JARDINAGE))

FEEDS = [
    ("https://www.dealabs.com/rss/groupe/outillage", "Outillage"),
    ("https://www.dealabs.com/rss/groupe/jardin-bricolage", "Jardinage"),
]

FIXAMI_URLS = [
    ("https://www.fixami.be/fr/offres/ete-plein-de-reductions.html", "Outillage"),
    ("https://www.fixami.be/fr/offres/bosch-pro-deals.html", "Outillage"),
]


H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def load_json(f, default):
    try:
        with open(f) as fp: return json.load(fp)
    except: return default

def save_json(f, data):
    with open(f, "w") as fp: json.dump(data, fp, ensure_ascii=False, indent=2)

def parse_price(s):
    if not s: return None
    try: return float(re.sub(r'[^\d,.]', '', str(s)).replace(',', '.'))
    except: return None

def is_relevant(text, category):
    t = text.lower()
    kw = KW_JARDINAGE if category == "Jardinage" else KW_OUTILLAGE
    return any(k in t for k in kw) or any(k in t for k in KW_ALL)

def calc_discount(old, new):
    try:
        o, n = float(str(old).replace(',', '.')), float(str(new).replace(',', '.'))
        if o > n > 0: return int((o - n) / o * 100)
    except: pass
    return 0

def fetch_url(url, timeout=25):
    """Fetch URL following redirects including 308."""
    req = urllib.request.Request(url, headers=H)
    for _ in range(6):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308):
                loc = e.headers.get("location", "")
                if loc:
                    if not loc.startswith("http"):
                        from urllib.parse import urljoin
                        loc = urljoin(url, loc)
                    req = urllib.request.Request(loc, headers=H)
                    url = loc
                else:
                    raise
            else:
                raise
    return ""

def parse_feed(html, category):
    deals = []
    items = re.findall(r'<item>(.*?)</item>', html, re.DOTALL)
    for item in items:
        t = re.search(r'<title><!\[CDATA\[([^\]]+)\]', item)
        if not t: continue
        title = t.group(1).strip()

        if not is_relevant(title, category): continue

        p = re.search(r'price="([^"]+)"', item)
        m = re.search(r'merchant name="([^"]+)"', item)
        l = re.search(r'<link>([^<]+)</link>', item)
        img = re.search(r'url="(https://[^"]+)"', item)
        d = re.search(r'<description><!\[CDATA\[(.*?)\]\]>', item, re.DOTALL)

        price_str = p.group(1) if p else ""
        merch = m.group(1) if m else ""
        link = l.group(1).strip() if l else ""
        image = img.group(1) if img else ""
        desc = re.sub(r'<[^>]+>', ' ', d.group(1)) if d else ""
        full_text = title + " " + desc

        current_price = parse_price(price_str)
        pct = 0

        pcts = re.findall(r'[-–]\s*(\d{2,3})\s*%', full_text)
        pcts += re.findall(r'(\d{2,3})\s*%\s*(?:de remise|reduction|off|moins|rabais)',
                           full_text, re.IGNORECASE)
        if pcts:
            pct = max(int(x) for x in pcts)

        if pct < 30 and current_price:
            all_prices = [parse_price(x) for x in re.findall(r'([\d]+[,\.][\d]{2})\s*€', full_text)]
            all_prices = sorted([x for x in all_prices if x and x > current_price * 1.1], reverse=True)
            if all_prices:
                pct = calc_discount(all_prices[0], current_price)

        if pct < 30:
            continue

        did = re.search(r'/(\d+)$', link)
        deal_id = did.group(1) if did else re.sub(r'[^\w]', '', title[:20] + price_str[:5])

        # Compute old price: use highest found price, or derive from pct
        old_price_str = ""
        if all_prices:
            old_price_str = f"{all_prices[0]:.2f}€"
        elif current_price and pct > 0:
            old_price_str = f"{current_price / (1 - pct / 100):.2f}€"

        deals.append({
            "id": deal_id,
            "title": title[:100],
            "price": price_str,
            "old_price": old_price_str,
            "pct": pct,
            "merch": merch,
            "category": category,
            "link": link,
            "image": image,
        })
    return deals

def parse_fixami(url, category):
    """Scrape Fixami offer page for deals >= 30%."""
    deals = []
    try:
        html = fetch_url(url)
        if not html:
            return deals

        # Extract products from JSON-LD CollectionPage
        products = []
        for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL):
            try:
                data = json.loads(m.group(1))
                if data.get('@type') == 'CollectionPage':
                    for item in data.get('mainEntity', {}).get('itemListElement', []):
                        p = item.get('item', {})
                        o = p.get('offers', {})
                        name = p.get('name', '')
                        price_val = o.get('price')
                        if name and price_val is not None:
                            try:
                                price = float(str(price_val).replace(',', '.'))
                            except:
                                price = 0
                            products.append({
                                'name': name,
                                'price': price,
                                'image': o.get('image', ''),
                                'url': p.get('url', '') or o.get('url', ''),
                            })
            except:
                pass

        print(f"  → Fixami: {len(products)} produits")

        for prod in products:
            name = prod['name']
            if not name or not is_relevant(name, category):
                continue

            # Find product in HTML by first 25 chars of name
            idx = html.find(name[:25])
            if idx < 0:
                continue

            # Look at window AFTER the product name for discount/price info
            window = html[idx: idx + 5000]

            # Find old price: "Prix de référence [amount]"
            old_price = 0.0
            ref_m = re.search(r'Prix de r[eé]f[eé]rence\s*([\d\s\xa0]+[,.][\d]*)', window, re.IGNORECASE)
            if ref_m:
                raw = re.sub(r'[^\d,.]', '', ref_m.group(1).replace('\xa0', '').replace(' ', ''))
                try:
                    old_price = float(raw.replace(',', '.'))
                except:
                    pass

            pct = 0

            # Explicit % badge: "-30%"
            pct_m = re.search(r'-(\d{1,3})\s*%', window)
            if pct_m:
                pct = int(pct_m.group(1))

            # Calculate from old/current price
            if pct < 30 and old_price > prod['price'] > 0:
                pct = int((old_price - prod['price']) / old_price * 100)

            # "X réduction" badge (amount reduced)
            if pct < 30 and old_price > 0:
                red_m = re.search(r'([\d]+[,.]?[\d]*)\s+r[eé]duction', window)
                if red_m:
                    try:
                        reduction = float(red_m.group(1).replace(',', '.'))
                        pct = int(reduction / old_price * 100)
                    except:
                        pass

            if pct < 30:
                continue

            deal_id = "fixami_" + re.sub(r'[^a-z0-9]', '', name[:20].lower()) + "_" + str(int(prod['price'] * 100))

            deals.append({
                "id": deal_id,
                "title": name[:100],
                "price": f"{prod['price']:.2f}€" if prod['price'] else "",
                "old_price": f"{old_price:.2f}€" if old_price else "",
                "pct": pct,
                "merch": "Fixami",
                "category": category,
                "link": prod['url'] or url,
                "image": prod['image'],
            })

    except Exception as e:
        print(f"  → Fixami erreur: {e}")

    return deals

def parse_rotopino_pages(base_url, merch_label="Rotopino", min_pct=20, max_pages=8):
    """Scrape Rotopino-structure pages for deals >= min_pct%."""
    deals = []
    try:
        for page in range(1, max_pages + 1):
            sep = "&" if "?" in base_url else "?"
            url = f"{base_url}{sep}page={page}" if page > 1 else base_url
            try:
                html = fetch_url(url, timeout=20)
            except Exception:
                break

            page_deals = 0
            for m in re.finditer(r'class="percent">(-\d{1,3})%</span>', html):
                pct = abs(int(m.group(1)))
                pos = m.start()
                block = html[pos:pos + 1000]

                old_m = re.search(r'class="old">([\d\s,\xa0]+)\s*€', block)
                curr_m = re.search(r'class="int-part">([\d\s]+)</span>\s*<span class="dec-part">([^<]*?)€', block)

                try:
                    old = float(re.sub(r'[^\d,.]', '', (old_m.group(1) if old_m else '0').replace('\xa0', '')).replace(',', '.'))
                    if curr_m:
                        int_p = re.sub(r'[^\d]', '', curr_m.group(1))
                        dec_p = re.sub(r'[^\d]', '', curr_m.group(2))
                        curr = float(f"{int_p}.{dec_p[:2] if dec_p else '00'}")
                    else:
                        curr = 0.0
                except:
                    old, curr = 0.0, 0.0

                if old > curr > 0:
                    pct = int((old - curr) / old * 100)

                if pct < min_pct:
                    continue

                before = html[max(0, pos - 2500):pos]
                prod_links = re.findall(r'href="(/[a-z0-9][^"]+,\d+)"[^>]*>\s*(?:<[^>]+>\s*)?([^<]{5,120})\s*</a>', before[-2000:])
                if prod_links:
                    prod_url = "https://www.rotopino.fr" + prod_links[-1][0]
                    name = prod_links[-1][1].strip()
                else:
                    alts = re.findall(r'alt="([^"]{5,120})"', before[-500:])
                    name = alts[-1] if alts else "?"
                    url_m2 = re.search(r'href="(/[a-z0-9][^"]+,\d+)"', before[-500:])
                    prod_url = "https://www.rotopino.fr" + url_m2.group(1) if url_m2 else url

                name = re.sub(r'&#(\d+);', lambda x: chr(int(x.group(1))), name)
                name = name.replace('&amp;', '&').replace('&quot;', '"').replace("&#39;", "'")

                if not is_relevant(name, "Outillage"):
                    continue

                img_m = (re.search(r'(?:data-default|src)="(/photo/product/[^"]+)"', before[-2000:]) or
                         re.search(r'(?:data-default|src)="(/photo/product/[^"]+)"', before[-6000:]))
                img = "https://www.rotopino.fr" + img_m.group(1) if img_m else ""

                slug = re.sub(r'[^a-z0-9]', '', name[:20].lower())
                deal_id = f"{merch_label.lower().replace(' ','_')}_{slug}_{int(curr * 100)}"
                deals.append({
                    "id": deal_id,
                    "title": name[:100],
                    "price": f"{curr:.2f}€" if curr else "",
                    "old_price": f"{old:.2f}€" if old else "",
                    "pct": pct,
                    "merch": merch_label,
                    "category": "Outillage",
                    "link": prod_url,
                    "image": img,
                })
                page_deals += 1

            print(f"  → {merch_label} p{page}: {page_deals} deals ≥{min_pct}%")
            if not re.search(rf'page={page + 1}', html):
                break

    except Exception as e:
        print(f"  → {merch_label} erreur: {e}")

    return deals

def parse_rotopino():
    return parse_rotopino_pages("https://www.rotopino.fr/offres/prix-baisse/", "Rotopino", min_pct=20, max_pages=8)

def tg(txt):
    data = urllib.parse.urlencode({
        "chat_id": CHAT, "text": txt,
        "parse_mode": "HTML", "disable_web_page_preview": "false"
    }).encode()
    with urllib.request.urlopen(
        urllib.request.Request(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=data),
        timeout=15) as r:
        return json.loads(r.read()).get("ok")

def generate_html(history):
    now = datetime.utcnow().strftime("%d/%m/%Y %H:%M UTC")
    deals_json = json.dumps(history[-300:], ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="fr"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Deals Outillage & Jardinage ≥30%</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh}}
header{{background:linear-gradient(135deg,#1e40af,#16a34a);padding:24px;text-align:center}}
header h1{{font-size:2rem;font-weight:700}}
header p{{opacity:.8;margin-top:6px;font-size:.85rem}}
.stats{{display:flex;gap:12px;justify-content:center;flex-wrap:wrap;padding:20px}}
.stat{{background:#1e293b;border-radius:12px;padding:16px 24px;text-align:center;border:1px solid #334155;min-width:120px}}
.stat .num{{font-size:2rem;font-weight:700;color:#60a5fa}}
.stat .label{{font-size:.75rem;color:#94a3b8;margin-top:4px}}
.controls{{padding:0 20px 16px;display:flex;gap:10px;flex-wrap:wrap;align-items:center}}
.controls input,.controls select{{padding:9px 14px;background:#1e293b;border:1px solid #334155;border-radius:8px;color:#e2e8f0;font-size:.9rem}}
.controls input{{flex:1;min-width:180px}}
.tabs{{display:flex;gap:8px;padding:0 20px 16px}}
.tab{{padding:8px 20px;border-radius:20px;border:1px solid #334155;cursor:pointer;font-size:.9rem;transition:all .2s}}
.tab.active{{background:#3b82f6;border-color:#3b82f6;font-weight:600}}
.tab:not(.active){{color:#94a3b8}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:14px;padding:0 20px 40px}}
.card{{background:#1e293b;border-radius:14px;border:1px solid #334155;overflow:hidden;transition:transform .2s,box-shadow .2s;text-decoration:none;color:inherit;display:block}}
.card:hover{{transform:translateY(-3px);box-shadow:0 10px 35px rgba(0,0,0,.4)}}
.card-img{{width:100%;height:150px;object-fit:contain;background:#0f172a;padding:10px}}
.placeholder{{width:100%;height:150px;background:#0f172a;display:flex;align-items:center;justify-content:center;font-size:2.5rem}}
.badge-row{{display:flex;align-items:center;gap:8px;padding:10px 12px 0}}
.badge{{color:#fff;font-weight:700;font-size:1rem;padding:3px 10px;border-radius:16px}}
.cat-badge{{font-size:.7rem;padding:2px 8px;border-radius:10px;font-weight:600}}
.cat-outillage{{background:#1e40af;color:#93c5fd}}
.cat-jardinage{{background:#14532d;color:#86efac}}
.card-body{{padding:10px 12px 12px}}
.card-title{{font-size:.88rem;font-weight:600;color:#f1f5f9;margin-bottom:8px;line-height:1.4;min-height:40px}}
.card-meta{{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}}
.price-block{{display:flex;flex-direction:column;gap:1px}}
.old-price{{font-size:.78rem;color:#64748b;text-decoration:line-through}}
.price{{font-size:1.1rem;font-weight:700;color:#34d399}}
.merch{{font-size:.72rem;color:#94a3b8;background:#0f172a;padding:2px 7px;border-radius:5px}}
.card-date{{font-size:.7rem;color:#64748b;margin-bottom:8px}}
.btn{{display:block;text-align:center;background:linear-gradient(135deg,#3b82f6,#8b5cf6);color:#fff;padding:9px;border-radius:7px;font-weight:600;font-size:.82rem}}
.empty{{text-align:center;padding:60px;color:#64748b}}
.footer{{text-align:center;padding:8px;color:#475569;font-size:.78rem;margin-bottom:10px}}
</style></head><body>
<header>
  <h1>🔧🌿 Deals Outillage & Jardinage ≥30%</h1>
  <p>Scan toutes les heures • Dealabs • Fixami • Rotopino • Hikoki • Leroy Merlin • Amazon • Lidl • Screwfix • ManoMano • Racetools • Bosch • Makita • DeWalt • Milwaukee • Ryobi • et plus</p>
</header>
<div class="stats">
  <div class="stat"><div class="num" id="total">0</div><div class="label">Total deals</div></div>
  <div class="stat"><div class="num" id="cnt-out">0</div><div class="label">🔧 Outillage</div></div>
  <div class="stat"><div class="num" id="cnt-jar">0</div><div class="label">🌿 Jardinage</div></div>
  <div class="stat"><div class="num" id="best">0%</div><div class="label">Meilleure remise</div></div>
  <div class="stat"><div class="num" id="shops">0</div><div class="label">Boutiques</div></div>
</div>
<div class="tabs">
  <div class="tab active" onclick="setTab('all',this)">Tout</div>
  <div class="tab" onclick="setTab('Outillage',this)">🔧 Outillage</div>
  <div class="tab" onclick="setTab('Jardinage',this)">🌿 Jardinage</div>
</div>
<div class="controls">
  <input type="text" id="search" placeholder="🔍 Rechercher (perceuse, tondeuse, bosch...)" oninput="filter()">
  <select id="sort" onchange="filter()">
    <option value="pct">Remise décroissante</option>
    <option value="date">Plus récents</option>
    <option value="price">Prix croissant</option>
  </select>
  <select id="store" onchange="filter()"><option value="">Toutes les boutiques</option></select>
</div>
<div class="grid" id="grid"></div>
<div class="footer">Dernière mise à jour : {now} • Source : Dealabs + Fixami + Rotopino direct • <a href="https://github.com/v7vbvryhc2-ai/deals-outillage" style="color:#60a5fa">GitHub</a></div>
<script>
const RAW={deals_json};
const deals=RAW.slice().reverse();
let activeTab='all';
const storeSelect=document.getElementById('store');
[...new Set(deals.map(d=>d.merch))].sort().forEach(s=>{{const o=document.createElement('option');o.value=s;o.textContent=s;storeSelect.appendChild(o)}});
function pctColor(p){{return p>=70?'#f97316':p>=50?'#ef4444':p>=40?'#dc2626':'#b91c1c'}}
function getOldPrice(d){{
  if(d.old_price)return d.old_price;
  if(d.price&&d.pct>0){{
    const c=parseFloat(d.price.replace(/[^0-9,.]/g,'').replace(',','.'));
    if(c&&c<9999)return(c/(1-d.pct/100)).toFixed(2).replace('.',',')+'€';
  }}
  return '';
}}
function parsePrice(s){{if(!s)return 9999;return parseFloat(s.replace(/[^0-9,\.]/g,'').replace(',','.'))||9999}}
function setTab(t,el){{activeTab=t;document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));el.classList.add('active');filter()}}
function filter(){{
  const q=document.getElementById('search').value.toLowerCase();
  const sort=document.getElementById('sort').value;
  const store=document.getElementById('store').value;
  let f=deals.filter(d=>
    (activeTab==='all'||d.category===activeTab)&&
    (d.title.toLowerCase().includes(q)||d.merch.toLowerCase().includes(q))&&
    (!store||d.merch===store)
  );
  if(sort==='pct')f.sort((a,b)=>b.pct-a.pct);
  else if(sort==='date')f.sort((a,b)=>(b.date||'').localeCompare(a.date||''));
  else f.sort((a,b)=>parsePrice(a.price)-parsePrice(b.price));
  render(f);
}}
function render(list){{
  const grid=document.getElementById('grid');
  if(!list.length){{grid.innerHTML='<div class="empty">Aucun deal trouvé 🔍</div>';return}}
  const icon=d=>d.category==='Jardinage'?'🌿':'🔧';
  grid.innerHTML=list.map(d=>`
    <a href="${{d.link}}" target="_blank" class="card">
      ${{d.image?`<img class="card-img" src="${{d.image}}" alt="${{d.title}}" loading="lazy" onerror="this.style.display='none'">`:`<div class="placeholder">${{icon(d)}}</div>`}}
      <div class="badge-row">
        <span class="badge" style="background:${{pctColor(d.pct)}}">-${{d.pct}}%</span>
        <span class="cat-badge ${{d.category==='Jardinage'?'cat-jardinage':'cat-outillage'}}">${{icon(d)}} ${{d.category||'Outillage'}}</span>
      </div>
      <div class="card-body">
        <div class="card-title">${{d.title}}</div>
        <div class="card-meta">
          <div class="price-block">
            ${{getOldPrice(d)?`<span class="old-price">${{getOldPrice(d)}}</span>`:''}}
            <span class="price">${{d.price||'?'}}</span>
          </div>
          <span class="merch">${{d.merch}}</span>
        </div>
        ${{d.date?`<div class="card-date">📅 ${{d.date}}</div>`:''}}
        <span class="btn">Voir le deal →</span>
      </div>
    </a>`).join('');
  const all=deals;
  document.getElementById('total').textContent=list.length;
  document.getElementById('cnt-out').textContent=all.filter(d=>d.category==='Outillage').length;
  document.getElementById('cnt-jar').textContent=all.filter(d=>d.category==='Jardinage').length;
  const pcts=list.map(d=>d.pct).filter(Boolean);
  document.getElementById('best').textContent=(pcts.length?Math.max(...pcts):0)+'%';
  document.getElementById('shops').textContent=new Set(list.map(d=>d.merch)).size;
}}
filter();
</script></body></html>"""

# Main
seen    = set(load_json(SEEN, []))
history = load_json(HISTORY, [])
now_str = datetime.utcnow().strftime("%d/%m/%Y %H:%M")
new     = []

all_deals = []

# Dealabs RSS feeds
for feed_url, category in FEEDS:
    try:
        print(f"Scan RSS {category}...")
        with urllib.request.urlopen(
            urllib.request.Request(feed_url, headers=H), timeout=20) as r:
            html = r.read().decode("utf-8", errors="replace")
        deals = parse_feed(html, category)
        print(f"  → {len(deals)} deals ≥30%")
        all_deals.extend(deals)
    except Exception as e:
        print(f"  → Erreur {category}: {e}")

# Fixami direct scan
print("Scan Fixami...")
for fixami_url, category in FIXAMI_URLS:
    try:
        deals = parse_fixami(fixami_url, category)
        print(f"  → {len(deals)} deals Fixami ≥30%")
        all_deals.extend(deals)
    except Exception as e:
        print(f"  → Fixami erreur: {e}")

# Rotopino direct scan (seuil ≥20%)
print("Scan Rotopino prix-baisse...")
try:
    rotopino_deals = parse_rotopino()
    print(f"  → {len(rotopino_deals)} deals Rotopino ≥20%")
    all_deals.extend(rotopino_deals)
except Exception as e:
    print(f"  → Rotopino erreur: {e}")

# Rotopino Hikoki brand page (seuil ≥10%)
print("Scan Rotopino Hikoki...")
try:
    hikoki_deals = parse_rotopino_pages(
        "https://www.rotopino.fr/hikoki",
        merch_label="Rotopino/Hikoki",
        min_pct=10,
        max_pages=3
    )
    print(f"  → {len(hikoki_deals)} deals Hikoki ≥10%")
    all_deals.extend(hikoki_deals)
except Exception as e:
    print(f"  → Rotopino Hikoki erreur: {e}")

for d in all_deals:
    if d["id"] not in seen:
        d["date"] = now_str
        new.append(d)
        seen.add(d["id"])
        history.append(d)

print(f"\nTotal: {len(all_deals)} deals, {len(new)} nouveaux")

if new:
    new.sort(key=lambda x: x["pct"], reverse=True)
    out = [d for d in new if d.get("category") == "Outillage"]
    jar = [d for d in new if d.get("category") == "Jardinage"]
    msg = f"🔧🌿 Deals ≥30% - {now_str}\n\n"
    if out:
        msg += "🔧 OUTILLAGE\n"
        for d in out[:5]:
            msg += f"[-{d['pct']}%] {d['title'][:60]}\n{d['price']} chez {d['merch']}\n{d['link']}\n\n"
    if jar:
        msg += "🌿 JARDINAGE\n"
        for d in jar[:5]:
            msg += f"[-{d['pct']}%] {d['title'][:60]}\n{d['price']} chez {d['merch']}\n{d['link']}\n\n"
    reste = len(new) - len(out[:5]) - len(jar[:5])
    if reste > 0: msg += f"... et {reste} autres\n\n"
    msg += f"👉 https://v7vbvryhc2-ai.github.io/deals-outillage/"
    if len(msg) > 4000: msg = msg[:4000]
    print("Telegram:", tg(msg))

save_json(SEEN, list(seen)[-1000:])
save_json(HISTORY, history[-300:])
with open("index.html", "w", encoding="utf-8") as f:
    f.write(generate_html(history))
print(f"Dashboard: {len(history)} deals total")
