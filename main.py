"""
main.py
-------
Interactive CLI for DotCo Swag lead scraper.
Scrapes Google Maps businesses in US cities via RapidAPI.

Setup:
    1. pip install -r requirements.txt
    2. Add RAPIDAPI_KEY to .env
    3. python build_data.py     → generates data/us_cities.json
    4. python main.py           → run the scraper

Output:
    resultados/resultados_YYYYMMDD_HHMMSS.csv
"""

import json
import os
import time
from datetime import datetime
from scraper import scrape_combinacion

BASE_DIR = os.path.dirname(__file__)
CIUDADES_PATH = os.path.join(BASE_DIR, "data", "us_cities.json")
RESULTADOS_DIR = os.path.join(BASE_DIR, "resultados")
CHECKPOINT_EXT = ".checkpoint.json"

# High-conversion markets (owner-operated, responsive to B2B)
MERCADOS_RECOMENDADOS = {
    "🔥 Sweet Spot (50k-250k) — Highest conversion": [
        ("Madison", "Wisconsin"),
        ("Boulder", "Colorado"),
        ("Fort Collins", "Colorado"),
        ("Eugene", "Oregon"),
        ("Bend", "Oregon"),
        ("Asheville", "North Carolina"),
        ("Chapel Hill", "North Carolina"),
        ("Santa Fe", "New Mexico"),
        ("Burlington", "Vermont"),
        ("Ithaca", "New York"),
        ("Bozeman", "Montana"),
        ("Flagstaff", "Arizona"),
        ("Sedona", "Arizona"),
    ],
    "⭐ Excellent (10k-50k) — Very high owner contact": [
        ("Aspen", "Colorado"),
        ("Montpelier", "Vermont"),
        ("Jackson", "Wyoming"),
        ("Moab", "Utah"),
        ("Park City", "Utah"),
        ("Vail", "Colorado"),
        ("Telluride", "Colorado"),
    ],
}

# ── Lead categories for branded merch buyers ─────────────────
CATEGORIAS = {
    "🌿 Smoke & Cannabis": [
        "tobacco shop",
        "cigar shop",
        "smoke shop",
        "hookah lounge",
        "cannabis dispensary",
        "marijuana dispensary",
        "weed dispensary",
        "CBD store",
        "head shop",
        "vape shop",
    ],
    "🏋️ Gyms & Fitness": [
        "gym",
        "CrossFit gym",
        "yoga studio",
        "pilates studio",
        "martial arts gym",
        "boxing gym",
        "personal training studio",
        "cycling studio",
    ],
    "🍔 Restaurants & Bars": [
        "restaurant",
        "bar",
        "brewery",
        "coffee shop",
        "food truck",
        "sports bar",
        "nightclub",
        "cocktail bar",
    ],
    "💈 Barbershops & Salons": [
        "barbershop",
        "hair salon",
        "nail salon",
        "tattoo shop",
        "beauty salon",
    ],
    "🏠 Real Estate": [
        "real estate agency",
        "real estate office",
        "property management company",
        "mortgage broker",
    ],
    "🚗 Auto": [
        "car dealership",
        "auto repair shop",
        "car wash",
        "auto parts store",
        "motorcycle dealership",
    ],
    "🏗️ Construction & Trades": [
        "construction company",
        "roofing contractor",
        "plumbing company",
        "electrician",
        "landscaping company",
        "HVAC contractor",
    ],
    "🏢 Corporate & Coworking": [
        "coworking space",
        "office building",
        "business center",
        "staffing agency",
        "marketing agency",
    ],
    "🎓 Schools & Sports": [
        "private school",
        "sports club",
        "youth sports league",
        "dance studio",
        "music school",
    ],
    "🏥 Medical & Dental": [
        "dental office",
        "medical clinic",
        "chiropractic office",
        "physical therapy",
        "optometry clinic",
    ],
}

ALL_CATEGORIES_FLAT = [cat for group in CATEGORIAS.values() for cat in group]


def linea(c="═", n=60):
    return c * n


# ── Checkpoint helpers ────────────────────────────────────
def _checkpoint_path(csv_path):
    return csv_path.replace(".csv", CHECKPOINT_EXT)


def guardar_checkpoint(csv_path, completadas, seen_ids):
    checkpoint_path = _checkpoint_path(csv_path)
    data = {
        "csv_path": csv_path,
        "completadas": [[c[0], c[1], c[2]] for c in completadas],
        "seen_ids": list(seen_ids),
    }
    with open(checkpoint_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def cargar_checkpoint(csv_path):
    checkpoint_path = _checkpoint_path(csv_path)
    if not os.path.exists(checkpoint_path):
        return set(), set()
    try:
        with open(checkpoint_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        completadas = set(tuple(c) for c in data.get("completadas", []))
        seen_ids = set(data.get("seen_ids", []))
        return completadas, seen_ids
    except Exception:
        return set(), set()


def buscar_csv_con_checkpoint():
    if not os.path.exists(RESULTADOS_DIR):
        return []

    matches = []
    for archivo in os.listdir(RESULTADOS_DIR):
        if archivo.endswith(".csv"):
            csv_path = os.path.join(RESULTADOS_DIR, archivo)
            checkpoint_path = _checkpoint_path(csv_path)
            if os.path.exists(checkpoint_path):
                matches.append((csv_path, checkpoint_path))
    return matches


def barra_progreso(contador, total, inicio_ts):
    if contador <= 0:
        return ""
    elapsed = time.time() - inicio_ts
    pct = (contador / total) * 100
    eta_segundos = (elapsed / contador) * (total - contador)

    barra_width = 20
    relleno = int((contador / total) * barra_width)
    barra = "█" * relleno + "░" * (barra_width - relleno)

    # Format ETA
    if eta_segundos < 60:
        eta_txt = f"{int(eta_segundos)}s"
    elif eta_segundos < 3600:
        eta_txt = f"{int(eta_segundos // 60)}m {int(eta_segundos % 60)}s"
    else:
        horas = int(eta_segundos // 3600)
        minutos = int((eta_segundos % 3600) // 60)
        eta_txt = f"{horas}h {minutos}m"

    return f"[{barra}] {pct:5.1f}% [{contador}/{total}] ETA {eta_txt}"


def filtrar_ciudades_por_poblacion(localidades, min_pop, max_pop):
    """Filter cities by population range to target owner-operated businesses."""
    return [
        (ciudad, estado) for ciudad, estado in localidades
        if min_pop <= (getattr(ciudad, 'poblacion', 100_000) if hasattr(ciudad, 'poblacion') else 100_000) <= max_pop
    ]


def elegir_rango_poblacion():
    """Ask user which city sizes to target — critical for owner contact rate."""
    print()
    print(linea())
    print("  TARGET MARKET SIZE")
    print("  (Smaller cities = owner answers email, higher conversion)")
    print(linea())
    print("  1. Tiny towns (10k-50k)       — Direct owner contact (40%+ conversion)")
    print("  2. Sweet spot (50k-250k)      — Owner-operated (25-35% conversion)")
    print("  3. Mid-large (250k-1M)        — Mixed ownership (10-20% conversion)")
    print("  4. Major metros (1M+)         — Corporate reception (2-5% conversion)")
    print("  5. All sizes                  — Comprehensive (baseline)")
    print("  6. Use recommended list       — Pre-curated high-conversion markets")

    opcion = pedir_opcion(["1", "2", "3", "4", "5", "6"])

    ranges = {
        "1": (10_000, 50_000, "Tiny towns"),
        "2": (50_000, 250_000, "Sweet spot"),
        "3": (250_000, 1_000_000, "Mid-large"),
        "4": (1_000_001, 100_000_000, "Major metros"),
        "5": (0, 100_000_000, "All sizes"),
        "6": None,  # Special case
    }

    if opcion == "6":
        return None, None, "RECOMMENDED"  # Signal to use recommended list

    min_pop, max_pop, label = ranges[opcion]
    print(f"  ✅ Targeting: {label} ({min_pop:,} - {max_pop:,} population)")
    return min_pop, max_pop, label


def elegir_mercados_recomendados():
    """Show pre-curated high-conversion markets."""
    print()
    print(linea())
    print("  RECOMMENDED HIGH-CONVERSION MARKETS")
    print("  (Owner-operated, responsive, merch-friendly)")
    print(linea())

    todas_ciudades = []
    for i, (tier, ciudades) in enumerate(MERCADOS_RECOMENDADOS.items(), 1):
        print(f"  {i}. {tier}")
        todas_ciudades.extend(ciudades)

    print()
    entrada = input("  Choose tier (1 or 2): ").strip()

    tier_map = {
        "1": MERCADOS_RECOMENDADOS["🔥 Sweet Spot (50k-250k) — Highest conversion"],
        "2": MERCADOS_RECOMENDADOS["⭐ Excellent (10k-50k) — Very high owner contact"],
    }

    if entrada in tier_map:
        seleccion = tier_map[entrada]
        print(f"  ✅ Selected {len(seleccion)} recommended cities")
        return seleccion

    print("  Using all recommended markets")
    return todas_ciudades


# ─────────────────────────────────────────────────────────

def cargar_ciudades():
    if not os.path.exists(CIUDADES_PATH):
        print("\n  ERROR: data/us_cities.json not found.")
        print("  Run first: python build_data.py")
        exit(1)
    with open(CIUDADES_PATH, encoding="utf-8") as f:
        return json.load(f)


def pedir_opcion(opciones_validas, mensaje="Choose"):
    while True:
        entrada = input(f"\n{mensaje}: ").strip()
        if entrada in opciones_validas:
            return entrada
        print(f"  Invalid option. Enter one of: {', '.join(opciones_validas)}")


def pedir_numeros(maximo, mensaje="Enter numbers separated by commas"):
    while True:
        entrada = input(f"\n{mensaje}: ").strip()
        try:
            numeros = [int(x.strip()) for x in entrada.split(",") if x.strip()]
            if all(1 <= n <= maximo for n in numeros) and numeros:
                return numeros
            print(f"  Enter numbers between 1 and {maximo}.")
        except ValueError:
            print("  Wrong format. Example: 1, 3, 5")


# ─────────────────────────────────────────────────────────────
# STEP 1 — Select States & Cities
# ─────────────────────────────────────────────────────────────

def filtrar_data_por_poblacion(data, min_pop, max_pop):
    """Filter the cities data structure by population range."""
    if min_pop is None or max_pop is None:
        return data  # No filtering

    filtered_data = {"provincias": []}
    for estado in data["provincias"]:
        filtered_locs = [
            loc for loc in estado["localidades"]
            if min_pop <= loc.get("poblacion", 100_000) <= max_pop
        ]
        if filtered_locs:
            filtered_data["provincias"].append({
                "nombre": estado["nombre"],
                "localidades": filtered_locs,
            })

    return filtered_data


def elegir_alcance(data):
    estados = data["provincias"]

    print()
    print(linea())
    print("  GEOGRAPHIC SCOPE")
    print(linea())
    print("  1. Entire US          — all states & cities")
    print("  2. Specific states    — choose which states")
    print("  3. Specific cities    — choose state then cities")

    opcion = pedir_opcion(["1", "2", "3"])

    if opcion == "1":
        seleccion = []
        for estado in estados:
            for loc in estado["localidades"]:
                seleccion.append((loc["nombre"], estado["nombre"]))
        print(f"\n  ✅ Selected all US ({len(seleccion)} cities)")
        return seleccion

    elif opcion == "2":
        print()
        print(linea("-"))
        print("  AVAILABLE STATES")
        print(linea("-"))
        for i, estado in enumerate(estados, 1):
            n = len(estado["localidades"])
            print(f"  {i:2}. {estado['nombre']} ({n} cities)")

        nums = pedir_numeros(len(estados), "Choose states (numbers separated by commas)")
        seleccion = []
        for n in nums:
            estado = estados[n - 1]
            for loc in estado["localidades"]:
                seleccion.append((loc["nombre"], estado["nombre"]))

        nombres = [estados[n - 1]["nombre"] for n in nums]
        print(f"\n  ✅ Selected: {', '.join(nombres)} ({len(seleccion)} cities)")
        return seleccion

    elif opcion == "3":
        print()
        print(linea("-"))
        print("  SELECT STATES FIRST")
        print(linea("-"))
        for i, estado in enumerate(estados, 1):
            print(f"  {i:2}. {estado['nombre']}")

        nums_estado = pedir_numeros(len(estados), "Choose states (can pick multiple)")
        seleccion = []

        for n_estado in nums_estado:
            estado = estados[n_estado - 1]
            localidades = estado["localidades"]
            principales = [l for l in localidades if l["es_principal"]]
            resto = [l for l in localidades if not l["es_principal"]]

            print()
            print(linea("-"))
            print(f"  CITIES IN {estado['nombre'].upper()}")
            print(linea("-"))
            print("  -- Major cities --")
            for i, loc in enumerate(principales, 1):
                print(f"  {i:3}. {loc['nombre']}")
            if resto:
                print()
                print("  -- Other cities --")
                for i, loc in enumerate(resto, len(principales) + 1):
                    print(f"  {i:3}. {loc['nombre']}")

            todas = principales + resto
            print()
            print("  0. All cities in this state")
            entrada = input("\n  Choose cities (numbers separated by commas, or 0 for all): ").strip()

            if entrada == "0":
                for loc in todas:
                    seleccion.append((loc["nombre"], estado["nombre"]))
                print(f"  ✅ All {len(todas)} cities in {estado['nombre']}")
            else:
                try:
                    nums_loc = [int(x.strip()) for x in entrada.split(",") if x.strip()]
                    nums_loc = [n for n in nums_loc if 1 <= n <= len(todas)]
                    for n in nums_loc:
                        loc = todas[n - 1]
                        seleccion.append((loc["nombre"], estado["nombre"]))
                    nombres_loc = [todas[n - 1]["nombre"] for n in nums_loc]
                    print(f"  ✅ Selected: {', '.join(nombres_loc)}")
                except ValueError:
                    print("  Invalid input, skipping this state.")

        return seleccion


# ─────────────────────────────────────────────────────────────
# STEP 2 — Select Categories
# ─────────────────────────────────────────────────────────────

def elegir_categorias():
    grupos = list(CATEGORIAS.keys())

    print()
    print(linea())
    print("  BUSINESS CATEGORIES")
    print(linea())
    print("   0. ALL categories (everything)")
    print()
    for i, grupo in enumerate(grupos, 1):
        n = len(CATEGORIAS[grupo])
        print(f"  {i:2}. {grupo}  ({n} search terms)")

    print()
    entrada = input("  Choose groups (numbers separated by commas, or 0 for all): ").strip()

    if entrada == "0":
        print(f"  ✅ All {len(ALL_CATEGORIES_FLAT)} category search terms selected")
        return ALL_CATEGORIES_FLAT[:]

    try:
        nums = [int(x.strip()) for x in entrada.split(",") if x.strip()]
        nums = [n for n in nums if 1 <= n <= len(grupos)]

        # Ask if they want to drill into individual terms within each group
        seleccion = []
        for n in nums:
            grupo = grupos[n - 1]
            terminos = CATEGORIAS[grupo]
            print()
            print(f"  {grupo} — search terms:")
            for j, t in enumerate(terminos, 1):
                print(f"    {j}. {t}")
            print(f"    0. All {len(terminos)} terms")
            sub = input(f"  Use all terms in this group? (Enter 0 or pick specific numbers): ").strip()
            if sub == "0" or not sub:
                seleccion.extend(terminos)
            else:
                try:
                    sub_nums = [int(x.strip()) for x in sub.split(",") if x.strip()]
                    for sn in sub_nums:
                        if 1 <= sn <= len(terminos):
                            seleccion.append(terminos[sn - 1])
                except ValueError:
                    seleccion.extend(terminos)

        print(f"\n  ✅ {len(seleccion)} search terms selected")
        return seleccion

    except ValueError:
        print("  Invalid input. Using all categories.")
        return ALL_CATEGORIES_FLAT[:]


# ─────────────────────────────────────────────────────────────
# STEP 3 — Result limit
# ─────────────────────────────────────────────────────────────

def elegir_limite():
    print()
    print(linea())
    print("  RESULT LIMIT")
    print(linea())
    print("  1. Maximum (all available)")
    print("  2. Specific number (e.g. 500, 2000, 5000)")

    opcion = pedir_opcion(["1", "2"])

    if opcion == "1":
        print("  ✅ No limit — all results will be saved")
        return None
    else:
        while True:
            entrada = input("\n  How many leads do you want? ").strip()
            try:
                n = int(entrada)
                if n > 0:
                    print(f"  ✅ Limit: {n:,} new businesses")
                    return n
                print("  Enter a number greater than 0.")
            except ValueError:
                print("  Invalid. Example: 1000")


# ─────────────────────────────────────────────────────────────
# STEP 4 — Min lead score filter
# ─────────────────────────────────────────────────────────────

def elegir_min_score():
    print()
    print(linea())
    print("  MIN LEAD SCORE FILTER")
    print(linea())
    print("  0. No filter (save all leads)")
    for i in range(1, 8):
        print(f"  {i}. Only save leads with score ≥ {i}")

    while True:
        entrada = input("\n  Choose minimum score: ").strip()
        try:
            n = int(entrada)
            if 0 <= n <= 7:
                if n == 0:
                    print("  ✅ No score filter — all leads will be saved")
                else:
                    print(f"  ✅ Filter: only leads with score ≥ {n}")
                return n
            print("  Enter a number between 0 and 7.")
        except ValueError:
            print("  Invalid. Example: 3")


# ─────────────────────────────────────────────────────────────
# STEP 5 — Confirm
# ─────────────────────────────────────────────────────────────

def confirmar(localidades, categorias, limite, min_score):
    n_loc = len(localidades)
    n_cat = len(categorias)
    n_busquedas = n_loc * n_cat
    limite_txt = f"{limite:,}" if limite else "no limit"
    score_txt = f"≥ {min_score}" if min_score > 0 else "no filter"

    print()
    print(linea())
    print("  PLAN SUMMARY")
    print(linea())
    print(f"  Cities:      {n_loc}")
    print(f"  Categories:  {n_cat}")
    print(f"  Searches:    {n_loc} × {n_cat} = {n_busquedas:,}")
    print(f"  Limit:       {limite_txt} new leads")
    print(f"  Min score:   {score_txt}")
    print()
    print(f"  Min API calls: {n_busquedas:,} (one per search, more if paginating)")
    print()

    # Show sample cities and categories
    sample_cities = [f"{c}, {s}" for c, s in localidades[:5]]
    if len(localidades) > 5:
        sample_cities.append(f"... +{len(localidades)-5} more")
    print(f"  Cities sample:      {' | '.join(sample_cities)}")

    sample_cats = categorias[:5]
    if len(categorias) > 5:
        sample_cats = sample_cats + [f"... +{len(categorias)-5} more"]
    print(f"  Categories sample:  {' | '.join(sample_cats)}")

    respuesta = input("\n  Ready to start? (y/n): ").strip().lower()
    return respuesta in ("y", "yes")


# ─────────────────────────────────────────────────────────────
# STEP 6 — Scrape
# ─────────────────────────────────────────────────────────────

def correr_scraping(localidades, categorias, limite, min_score=0):
    os.makedirs(RESULTADOS_DIR, exist_ok=True)

    # Check for resumable checkpoints
    checkpoints = buscar_csv_con_checkpoint()
    archivo_csv = None
    completadas_set = set()
    seen_ids = set()

    if checkpoints:
        print()
        print(linea())
        print("  PREVIOUS SESSIONS FOUND")
        print(linea())
        for i, (csv_path, _) in enumerate(checkpoints, 1):
            basename = os.path.basename(csv_path)
            print(f"  {i}. {basename}")
        print()
        resume = input("  Resume a previous session? (y/n): ").strip().lower()
        if resume in ("y", "yes"):
            if len(checkpoints) == 1:
                archivo_csv, _ = checkpoints[0]
            else:
                while True:
                    try:
                        num = int(input("  Select session (number): ").strip())
                        if 1 <= num <= len(checkpoints):
                            archivo_csv, _ = checkpoints[num - 1]
                            break
                    except ValueError:
                        pass
                    print("  Invalid selection.")

            # Load checkpoint
            completadas_set, seen_ids = cargar_checkpoint(archivo_csv)
            print(f"  ✅ Resuming: {len(completadas_set)} completed, {len(seen_ids)} seen IDs loaded")

    # If not resuming, create new CSV
    if archivo_csv is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archivo_csv = os.path.join(RESULTADOS_DIR, f"dotco_leads_{timestamp}.csv")

    # Build combination list to process
    total_combinaciones = len(localidades) * len(categorias)
    combinaciones_pendientes = [
        (localidad, provincia, categoria)
        for localidad, provincia in localidades
        for categoria in categorias
        if (localidad, categoria, provincia) not in completadas_set
    ]

    contador = 0
    total_nuevos = 0
    total_duplicados = 0
    total_skipped_score = 0
    inicio_ts = time.time()

    print()
    print(linea())
    print("  SCRAPING IN PROGRESS")
    print(linea())
    print(f"  Saving to: {archivo_csv}")
    print()

    for localidad, provincia, categoria in combinaciones_pendientes:
        if limite is not None and len(seen_ids) >= limite:
            print(f"\n  🏁 Limit of {limite:,} leads reached. Stopping.")
            break

        contador += 1
        combo_key = (localidad, categoria, provincia)

        nuevos, duplicados, skipped_score = scrape_combinacion(
            localidad=localidad,
            categoria=categoria,
            provincia=provincia,
            archivo_csv=archivo_csv,
            seen_ids=seen_ids,
            limite_total=limite,
            min_score=min_score,
        )

        completadas_set.add(combo_key)
        guardar_checkpoint(archivo_csv, completadas_set, seen_ids)

        total_nuevos += nuevos
        total_duplicados += duplicados
        total_skipped_score += skipped_score

        # Print progress with bar
        barra = barra_progreso(contador, len(combinaciones_pendientes), inicio_ts)
        print(f"\r{barra}", end="", flush=True)

        # Print result details on new line
        total_found = nuevos + duplicados
        print(f"\n     → {total_found} found ({nuevos} new, {duplicados} dup, {skipped_score} skip) | Total saved: {len(seen_ids):,}")

    # Final report
    elapsed = time.time() - inicio_ts
    elapsed_txt = f"{int(elapsed // 60)}m {int(elapsed % 60)}s"

    print()
    print(linea())
    print("  FINAL REPORT")
    print(linea())
    print(f"  Total leads saved      : {total_nuevos:,}")
    print(f"  Leads skipped (score)  : {total_skipped_score:,}")
    print(f"  Duplicate businesses   : {total_duplicados:,}")
    print(f"  Searches completed     : {contador}/{len(combinaciones_pendientes)}")
    print(f"  Elapsed time           : {elapsed_txt}")
    print(f"  Output file            : {archivo_csv}")
    print(linea())

    # Clean up checkpoint file on success
    checkpoint_path = _checkpoint_path(archivo_csv)
    if os.path.exists(checkpoint_path):
        os.remove(checkpoint_path)

    print()

    # Offer XLSX export
    exportar_xlsx = input("  Export to XLSX? (y/n): ").strip().lower()
    if exportar_xlsx in ("y", "yes"):
        from export import csv_to_xlsx
        xlsx_path = archivo_csv.replace(".csv", ".xlsx")
        csv_to_xlsx(archivo_csv, xlsx_path)
        print(f"  ✅ XLSX saved: {xlsx_path}")

    # Offer AI enrichment (strictly opt-in; default 'n' at every prompt)
    csv_para_export = archivo_csv
    try:
        import ai_client
        ai_available = ai_client.is_enabled()
    except ImportError:
        ai_available = False

    if ai_available:
        ai_yn = input("  Enrich leads with AI? (y/n) [default: n]: ").strip().lower()
        if ai_yn in ("y", "yes"):
            features = []
            r = input("    First-name inference? (y/n) [default y]: ").strip().lower()
            if r not in ("n", "no"):
                features.append("first_name")
            r = input("    Personalized opener? (y/n) [default n — costs more]: ").strip().lower()
            if r in ("y", "yes"):
                features.append("opener")
            r = input("    Qualify leads? (y/n) [default n]: ").strip().lower()
            if r in ("y", "yes"):
                features.append("qualify")

            if features:
                import csv as _csv
                with open(archivo_csv, encoding="utf-8") as _f:
                    num_rows = sum(1 for _ in _csv.DictReader(_f))
                from enrich import estimate_total_cost, enrich_csv
                est_cost = estimate_total_cost(num_rows, features)
                print(f"    {num_rows} rows × features: {', '.join(features)}")
                print(f"    Estimated cost: ~${est_cost:.4f} USD")
                confirm = input(f"    Confirm and spend ~${est_cost:.4f}? (y/n) [default: n]: ").strip().lower()
                if confirm in ("y", "yes"):
                    enriched = enrich_csv(archivo_csv, features=tuple(features))
                    if enriched:
                        csv_para_export = enriched
                else:
                    print("    Skipped AI enrichment (no charges).")
            else:
                print("    No AI features selected.")

    # Offer Smartlead export
    exportar_smartlead = input("  Export to Smartlead CSV? (y/n): ").strip().lower()
    if exportar_smartlead in ("y", "yes"):
        from export_smartlead import export as export_smartlead
        sl_min_score = 0
        entrada = input("  Min lead score for Smartlead (0-7, default 0): ").strip()
        if entrada:
            try:
                n = int(entrada)
                if 0 <= n <= 7:
                    sl_min_score = n
            except ValueError:
                print("  Invalid number — using 0.")
        sl_require_qualified = False
        if csv_para_export != archivo_csv:
            rq = input("  Drop rows AI marked as disqualified? (y/n) [default n]: ").strip().lower()
            sl_require_qualified = rq in ("y", "yes")
        export_smartlead(csv_para_export, sl_min_score, require_qualified=sl_require_qualified)

    print()


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main():
    print()
    print(linea())
    print("  DOTCO SWAG — LEAD SCRAPER")
    print("  Source: Google Maps via RapidAPI")
    print("  Target: US businesses → branded merch leads")
    print("  Strategy: Small-to-mid cities = owner answers email")
    print(linea())

    data = cargar_ciudades()

    # STEP 1: Choose market size (critical for conversion rate)
    min_pop, max_pop, pop_label = elegir_rango_poblacion()

    # If user chose "recommended markets", use pre-curated list
    if pop_label == "RECOMMENDED":
        localidades = elegir_mercados_recomendados()
    else:
        # Filter data by population and show interactive selection
        data_filtrada = filtrar_data_por_poblacion(data, min_pop, max_pop)
        localidades = elegir_alcance(data_filtrada)

    categorias = elegir_categorias()
    limite = elegir_limite()
    min_score = elegir_min_score()

    if not confirmar(localidades, categorias, limite, min_score):
        print("\n  Cancelled. No API calls were made.\n")
        return

    correr_scraping(localidades, categorias, limite, min_score)


if __name__ == "__main__":
    main()
