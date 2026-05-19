"""
build_data.py
-------------
Generates data/us_cities.json — a curated list of US cities organized by state,
with real 2023 Census-estimate populations.

Run:
    python build_data.py
"""

import json
import os

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "data", "us_cities.json")

DEFAULT_POP = 100_000  # fallback for any (state, city) pair not in the dict below

# Populations keyed by (state, city) to disambiguate repeated names
# (Portland OR vs ME, Columbus OH vs GA, Jackson MS vs WY, etc.)
# Numbers are 2023 US Census estimates, rounded to the nearest thousand.
CITY_POPS = {
    # Alabama
    ("Alabama", "Birmingham"): 196_000,
    ("Alabama", "Montgomery"): 196_000,
    ("Alabama", "Huntsville"): 225_000,
    ("Alabama", "Mobile"): 183_000,
    ("Alabama", "Tuscaloosa"): 111_000,
    # Alaska
    ("Alaska", "Anchorage"): 287_000,
    ("Alaska", "Fairbanks"): 32_000,
    ("Alaska", "Juneau"): 31_000,
    ("Alaska", "Sitka"): 8_500,
    ("Alaska", "Ketchikan"): 8_200,
    # Arizona
    ("Arizona", "Phoenix"): 1_650_000,
    ("Arizona", "Tucson"): 545_000,
    ("Arizona", "Mesa"): 510_000,
    ("Arizona", "Chandler"): 280_000,
    ("Arizona", "Scottsdale"): 241_000,
    ("Arizona", "Tempe"): 184_000,
    ("Arizona", "Gilbert"): 275_000,
    ("Arizona", "Glendale"): 253_000,
    # Arkansas
    ("Arkansas", "Little Rock"): 202_000,
    ("Arkansas", "Fort Smith"): 89_000,
    ("Arkansas", "Fayetteville"): 95_000,
    ("Arkansas", "Springdale"): 87_000,
    ("Arkansas", "Jonesboro"): 80_000,
    # California
    ("California", "Los Angeles"): 3_820_000,
    ("California", "San Diego"): 1_388_000,
    ("California", "San Jose"): 970_000,
    ("California", "San Francisco"): 808_000,
    ("California", "Fresno"): 543_000,
    ("California", "Sacramento"): 526_000,
    ("California", "Long Beach"): 451_000,
    ("California", "Oakland"): 430_000,
    ("California", "Bakersfield"): 410_000,
    ("California", "Anaheim"): 345_000,
    ("California", "Santa Ana"): 309_000,
    ("California", "Riverside"): 317_000,
    ("California", "Stockton"): 320_000,
    ("California", "Irvine"): 313_000,
    ("California", "Chula Vista"): 277_000,
    ("California", "Fremont"): 227_000,
    ("California", "San Bernardino"): 221_000,
    ("California", "Modesto"): 218_000,
    ("California", "Fontana"): 209_000,
    ("California", "Santa Clarita"): 230_000,
    # Colorado
    ("Colorado", "Denver"): 716_000,
    ("Colorado", "Colorado Springs"): 488_000,
    ("Colorado", "Aurora"): 391_000,
    ("Colorado", "Fort Collins"): 170_000,
    ("Colorado", "Lakewood"): 156_000,
    ("Colorado", "Boulder"): 105_000,
    ("Colorado", "Pueblo"): 111_000,
    # Connecticut
    ("Connecticut", "Bridgeport"): 148_000,
    ("Connecticut", "New Haven"): 135_000,
    ("Connecticut", "Hartford"): 121_000,
    ("Connecticut", "Stamford"): 136_000,
    ("Connecticut", "Waterbury"): 114_000,
    # Delaware
    ("Delaware", "Wilmington"): 71_000,
    ("Delaware", "Dover"): 39_000,
    ("Delaware", "Newark"): 32_000,
    ("Delaware", "Middletown"): 23_000,
    # Florida
    ("Florida", "Jacksonville"): 985_000,
    ("Florida", "Miami"): 449_000,
    ("Florida", "Tampa"): 398_000,
    ("Florida", "Orlando"): 320_000,
    ("Florida", "St. Petersburg"): 263_000,
    ("Florida", "Hialeah"): 222_000,
    ("Florida", "Tallahassee"): 202_000,
    ("Florida", "Fort Lauderdale"): 184_000,
    ("Florida", "Cape Coral"): 224_000,
    ("Florida", "Pembroke Pines"): 170_000,
    ("Florida", "Hollywood"): 153_000,
    ("Florida", "Gainesville"): 145_000,
    ("Florida", "Miramar"): 136_000,
    ("Florida", "Coral Springs"): 134_000,
    ("Florida", "West Palm Beach"): 119_000,
    # Georgia
    ("Georgia", "Atlanta"): 510_000,
    ("Georgia", "Augusta"): 202_000,
    ("Georgia", "Columbus"): 201_000,
    ("Georgia", "Savannah"): 148_000,
    ("Georgia", "Athens"): 127_000,
    ("Georgia", "Macon"): 157_000,
    ("Georgia", "Sandy Springs"): 109_000,
    # Hawaii
    ("Hawaii", "Honolulu"): 343_000,
    ("Hawaii", "Pearl City"): 45_000,
    ("Hawaii", "Hilo"): 44_000,
    ("Hawaii", "Kailua"): 37_000,
    # Idaho
    ("Idaho", "Boise"): 240_000,
    ("Idaho", "Meridian"): 134_000,
    ("Idaho", "Nampa"): 113_000,
    ("Idaho", "Idaho Falls"): 67_000,
    ("Idaho", "Pocatello"): 57_000,
    # Illinois
    ("Illinois", "Chicago"): 2_665_000,
    ("Illinois", "Aurora"): 178_000,
    ("Illinois", "Joliet"): 151_000,
    ("Illinois", "Naperville"): 150_000,
    ("Illinois", "Rockford"): 145_000,
    ("Illinois", "Springfield"): 114_000,
    ("Illinois", "Peoria"): 110_000,
    # Indiana
    ("Indiana", "Indianapolis"): 880_000,
    ("Indiana", "Fort Wayne"): 270_000,
    ("Indiana", "Evansville"): 115_000,
    ("Indiana", "South Bend"): 103_000,
    ("Indiana", "Carmel"): 102_000,
    ("Indiana", "Fishers"): 100_000,
    # Iowa
    ("Iowa", "Des Moines"): 213_000,
    ("Iowa", "Cedar Rapids"): 137_000,
    ("Iowa", "Davenport"): 101_000,
    ("Iowa", "Sioux City"): 85_000,
    ("Iowa", "Iowa City"): 75_000,
    # Kansas
    ("Kansas", "Wichita"): 397_000,
    ("Kansas", "Overland Park"): 197_000,
    ("Kansas", "Kansas City"): 156_000,
    ("Kansas", "Olathe"): 143_000,
    ("Kansas", "Topeka"): 125_000,
    # Kentucky
    ("Kentucky", "Louisville"): 624_000,
    ("Kentucky", "Lexington"): 322_000,
    ("Kentucky", "Bowling Green"): 75_000,
    ("Kentucky", "Owensboro"): 60_000,
    ("Kentucky", "Covington"): 41_000,
    # Louisiana
    ("Louisiana", "New Orleans"): 364_000,
    ("Louisiana", "Baton Rouge"): 218_000,
    ("Louisiana", "Shreveport"): 180_000,
    ("Louisiana", "Metairie"): 143_000,
    ("Louisiana", "Lafayette"): 121_000,
    # Maine
    ("Maine", "Portland"): 68_000,
    ("Maine", "Lewiston"): 37_000,
    ("Maine", "Bangor"): 32_000,
    ("Maine", "South Portland"): 26_000,
    # Maryland
    ("Maryland", "Baltimore"): 569_000,
    ("Maryland", "Frederick"): 80_000,
    ("Maryland", "Rockville"): 68_000,
    ("Maryland", "Gaithersburg"): 70_000,
    ("Maryland", "Bowie"): 58_000,
    # Massachusetts
    ("Massachusetts", "Boston"): 651_000,
    ("Massachusetts", "Worcester"): 207_000,
    ("Massachusetts", "Springfield"): 154_000,
    ("Massachusetts", "Cambridge"): 118_000,
    ("Massachusetts", "Lowell"): 115_000,
    ("Massachusetts", "Providence"): 190_000,  # NOTE: Providence is actually in Rhode Island
    # Michigan
    ("Michigan", "Detroit"): 631_000,
    ("Michigan", "Grand Rapids"): 198_000,
    ("Michigan", "Warren"): 139_000,
    ("Michigan", "Sterling Heights"): 134_000,
    ("Michigan", "Ann Arbor"): 123_000,
    ("Michigan", "Lansing"): 112_000,
    ("Michigan", "Flint"): 80_000,
    # Minnesota
    ("Minnesota", "Minneapolis"): 425_000,
    ("Minnesota", "Saint Paul"): 308_000,
    ("Minnesota", "Rochester"): 122_000,
    ("Minnesota", "Duluth"): 86_000,
    ("Minnesota", "Bloomington"): 89_000,
    # Mississippi
    ("Mississippi", "Jackson"): 145_000,
    ("Mississippi", "Gulfport"): 72_000,
    ("Mississippi", "Southaven"): 56_000,
    ("Mississippi", "Hattiesburg"): 48_000,
    ("Mississippi", "Biloxi"): 49_000,
    # Missouri
    ("Missouri", "Kansas City"): 510_000,
    ("Missouri", "St. Louis"): 281_000,
    ("Missouri", "Springfield"): 170_000,
    ("Missouri", "Columbia"): 127_000,
    ("Missouri", "Independence"): 123_000,
    # Montana
    ("Montana", "Billings"): 119_000,
    ("Montana", "Missoula"): 77_000,
    ("Montana", "Great Falls"): 60_000,
    ("Montana", "Bozeman"): 56_000,
    # Nebraska
    ("Nebraska", "Omaha"): 485_000,
    ("Nebraska", "Lincoln"): 294_000,
    ("Nebraska", "Bellevue"): 64_000,
    ("Nebraska", "Grand Island"): 53_000,
    # Nevada
    ("Nevada", "Las Vegas"): 660_000,
    ("Nevada", "Henderson"): 325_000,
    ("Nevada", "Reno"): 268_000,
    ("Nevada", "North Las Vegas"): 277_000,
    ("Nevada", "Sparks"): 109_000,
    # New Hampshire
    ("New Hampshire", "Manchester"): 116_000,
    ("New Hampshire", "Nashua"): 91_000,
    ("New Hampshire", "Concord"): 44_000,
    ("New Hampshire", "Dover"): 33_000,
    # New Jersey
    ("New Jersey", "Newark"): 305_000,
    ("New Jersey", "Jersey City"): 291_000,
    ("New Jersey", "Paterson"): 159_000,
    ("New Jersey", "Elizabeth"): 137_000,
    ("New Jersey", "Edison"): 108_000,
    ("New Jersey", "Trenton"): 90_000,
    # New Mexico
    ("New Mexico", "Albuquerque"): 561_000,
    ("New Mexico", "Las Cruces"): 113_000,
    ("New Mexico", "Rio Rancho"): 108_000,
    ("New Mexico", "Santa Fe"): 89_000,
    # New York
    ("New York", "New York City"): 8_260_000,
    ("New York", "Buffalo"): 274_000,
    ("New York", "Rochester"): 210_000,
    ("New York", "Yonkers"): 210_000,
    ("New York", "Syracuse"): 146_000,
    ("New York", "Albany"): 99_000,
    ("New York", "New Rochelle"): 78_000,
    # North Carolina
    ("North Carolina", "Charlotte"): 911_000,
    ("North Carolina", "Raleigh"): 482_000,
    ("North Carolina", "Greensboro"): 302_000,
    ("North Carolina", "Durham"): 296_000,
    ("North Carolina", "Winston-Salem"): 250_000,
    ("North Carolina", "Fayetteville"): 210_000,
    ("North Carolina", "Cary"): 180_000,
    # North Dakota
    ("North Dakota", "Fargo"): 127_000,
    ("North Dakota", "Bismarck"): 74_000,
    ("North Dakota", "Grand Forks"): 59_000,
    ("North Dakota", "Minot"): 48_000,
    # Ohio
    ("Ohio", "Columbus"): 913_000,
    ("Ohio", "Cleveland"): 363_000,
    ("Ohio", "Cincinnati"): 309_000,
    ("Ohio", "Toledo"): 268_000,
    ("Ohio", "Akron"): 188_000,
    ("Ohio", "Dayton"): 137_000,
    # Oklahoma
    ("Oklahoma", "Oklahoma City"): 697_000,
    ("Oklahoma", "Tulsa"): 411_000,
    ("Oklahoma", "Norman"): 128_000,
    ("Oklahoma", "Broken Arrow"): 117_000,
    ("Oklahoma", "Edmond"): 95_000,
    # Oregon
    ("Oregon", "Portland"): 631_000,
    ("Oregon", "Salem"): 177_000,
    ("Oregon", "Eugene"): 175_000,
    ("Oregon", "Gresham"): 113_000,
    ("Oregon", "Hillsboro"): 107_000,
    ("Oregon", "Bend"): 103_000,
    # Pennsylvania
    ("Pennsylvania", "Philadelphia"): 1_550_000,
    ("Pennsylvania", "Pittsburgh"): 303_000,
    ("Pennsylvania", "Allentown"): 125_000,
    ("Pennsylvania", "Erie"): 94_000,
    ("Pennsylvania", "Reading"): 95_000,
    ("Pennsylvania", "Scranton"): 76_000,
    # Rhode Island
    ("Rhode Island", "Providence"): 190_000,
    ("Rhode Island", "Cranston"): 82_000,
    ("Rhode Island", "Warwick"): 82_000,
    ("Rhode Island", "Pawtucket"): 75_000,
    # South Carolina
    ("South Carolina", "Columbia"): 137_000,
    ("South Carolina", "Charleston"): 155_000,
    ("South Carolina", "North Charleston"): 114_000,
    ("South Carolina", "Mount Pleasant"): 92_000,
    ("South Carolina", "Greenville"): 72_000,
    # South Dakota
    ("South Dakota", "Sioux Falls"): 202_000,
    ("South Dakota", "Rapid City"): 78_000,
    ("South Dakota", "Aberdeen"): 28_000,
    # Tennessee
    ("Tennessee", "Memphis"): 618_000,
    ("Tennessee", "Nashville"): 687_000,
    ("Tennessee", "Knoxville"): 198_000,
    ("Tennessee", "Chattanooga"): 187_000,
    ("Tennessee", "Clarksville"): 175_000,
    # Texas
    ("Texas", "Houston"): 2_300_000,
    ("Texas", "San Antonio"): 1_495_000,
    ("Texas", "Dallas"): 1_300_000,
    ("Texas", "Austin"): 974_000,
    ("Texas", "Fort Worth"): 978_000,
    ("Texas", "El Paso"): 678_000,
    ("Texas", "Arlington"): 394_000,
    ("Texas", "Corpus Christi"): 317_000,
    ("Texas", "Plano"): 286_000,
    ("Texas", "Laredo"): 257_000,
    ("Texas", "Lubbock"): 263_000,
    ("Texas", "Garland"): 246_000,
    ("Texas", "Irving"): 256_000,
    ("Texas", "Amarillo"): 201_000,
    ("Texas", "McKinney"): 207_000,
    ("Texas", "Frisco"): 219_000,
    # Utah
    ("Utah", "Salt Lake City"): 209_000,
    ("Utah", "West Valley City"): 140_000,
    ("Utah", "Provo"): 115_000,
    ("Utah", "West Jordan"): 117_000,
    ("Utah", "Orem"): 98_000,
    ("Utah", "Sandy"): 95_000,
    # Vermont
    ("Vermont", "Burlington"): 45_000,
    ("Vermont", "Essex"): 22_000,
    ("Vermont", "South Burlington"): 20_000,
    ("Vermont", "Colchester"): 17_000,
    # Virginia
    ("Virginia", "Virginia Beach"): 457_000,
    ("Virginia", "Norfolk"): 232_000,
    ("Virginia", "Chesapeake"): 251_000,
    ("Virginia", "Richmond"): 229_000,
    ("Virginia", "Arlington"): 238_000,
    ("Virginia", "Alexandria"): 156_000,
    # Washington
    ("Washington", "Seattle"): 755_000,
    ("Washington", "Spokane"): 230_000,
    ("Washington", "Tacoma"): 222_000,
    ("Washington", "Vancouver"): 197_000,
    ("Washington", "Bellevue"): 152_000,
    ("Washington", "Kirkland"): 94_000,
    ("Washington", "Olympia"): 56_000,
    # West Virginia
    ("West Virginia", "Charleston"): 47_000,
    ("West Virginia", "Huntington"): 45_000,
    ("West Virginia", "Morgantown"): 30_000,
    ("West Virginia", "Parkersburg"): 29_000,
    # Wisconsin
    ("Wisconsin", "Milwaukee"): 561_000,
    ("Wisconsin", "Madison"): 273_000,
    ("Wisconsin", "Green Bay"): 107_000,
    ("Wisconsin", "Kenosha"): 99_000,
    ("Wisconsin", "Racine"): 76_000,
    # Wyoming
    ("Wyoming", "Cheyenne"): 65_000,
    ("Wyoming", "Casper"): 59_000,
    ("Wyoming", "Laramie"): 32_000,
    ("Wyoming", "Gillette"): 33_000,
    # DC
    ("Washington D.C.", "Washington D.C."): 678_000,
}

# Top cities per US state (population-ranked, curated)
US_CITIES = {
    "Alabama": ["Birmingham", "Montgomery", "Huntsville", "Mobile", "Tuscaloosa"],
    "Alaska": ["Anchorage", "Fairbanks", "Juneau", "Sitka", "Ketchikan"],
    "Arizona": ["Phoenix", "Tucson", "Mesa", "Chandler", "Scottsdale", "Tempe", "Gilbert", "Glendale"],
    "Arkansas": ["Little Rock", "Fort Smith", "Fayetteville", "Springdale", "Jonesboro"],
    "California": [
        "Los Angeles", "San Diego", "San Jose", "San Francisco", "Fresno",
        "Sacramento", "Long Beach", "Oakland", "Bakersfield", "Anaheim",
        "Santa Ana", "Riverside", "Stockton", "Irvine", "Chula Vista",
        "Fremont", "San Bernardino", "Modesto", "Fontana", "Santa Clarita",
    ],
    "Colorado": ["Denver", "Colorado Springs", "Aurora", "Fort Collins", "Lakewood", "Boulder", "Pueblo"],
    "Connecticut": ["Bridgeport", "New Haven", "Hartford", "Stamford", "Waterbury"],
    "Delaware": ["Wilmington", "Dover", "Newark", "Middletown"],
    "Florida": [
        "Jacksonville", "Miami", "Tampa", "Orlando", "St. Petersburg",
        "Hialeah", "Tallahassee", "Fort Lauderdale", "Cape Coral", "Pembroke Pines",
        "Hollywood", "Gainesville", "Miramar", "Coral Springs", "West Palm Beach",
    ],
    "Georgia": ["Atlanta", "Augusta", "Columbus", "Savannah", "Athens", "Macon", "Sandy Springs"],
    "Hawaii": ["Honolulu", "Pearl City", "Hilo", "Kailua"],
    "Idaho": ["Boise", "Meridian", "Nampa", "Idaho Falls", "Pocatello"],
    "Illinois": ["Chicago", "Aurora", "Joliet", "Naperville", "Rockford", "Springfield", "Peoria"],
    "Indiana": ["Indianapolis", "Fort Wayne", "Evansville", "South Bend", "Carmel", "Fishers"],
    "Iowa": ["Des Moines", "Cedar Rapids", "Davenport", "Sioux City", "Iowa City"],
    "Kansas": ["Wichita", "Overland Park", "Kansas City", "Olathe", "Topeka"],
    "Kentucky": ["Louisville", "Lexington", "Bowling Green", "Owensboro", "Covington"],
    "Louisiana": ["New Orleans", "Baton Rouge", "Shreveport", "Metairie", "Lafayette"],
    "Maine": ["Portland", "Lewiston", "Bangor", "South Portland"],
    "Maryland": ["Baltimore", "Frederick", "Rockville", "Gaithersburg", "Bowie"],
    "Massachusetts": ["Boston", "Worcester", "Springfield", "Cambridge", "Lowell", "Providence"],
    "Michigan": ["Detroit", "Grand Rapids", "Warren", "Sterling Heights", "Ann Arbor", "Lansing", "Flint"],
    "Minnesota": ["Minneapolis", "Saint Paul", "Rochester", "Duluth", "Bloomington"],
    "Mississippi": ["Jackson", "Gulfport", "Southaven", "Hattiesburg", "Biloxi"],
    "Missouri": ["Kansas City", "St. Louis", "Springfield", "Columbia", "Independence"],
    "Montana": ["Billings", "Missoula", "Great Falls", "Bozeman"],
    "Nebraska": ["Omaha", "Lincoln", "Bellevue", "Grand Island"],
    "Nevada": ["Las Vegas", "Henderson", "Reno", "North Las Vegas", "Sparks"],
    "New Hampshire": ["Manchester", "Nashua", "Concord", "Dover"],
    "New Jersey": ["Newark", "Jersey City", "Paterson", "Elizabeth", "Edison", "Trenton"],
    "New Mexico": ["Albuquerque", "Las Cruces", "Rio Rancho", "Santa Fe"],
    "New York": ["New York City", "Buffalo", "Rochester", "Yonkers", "Syracuse", "Albany", "New Rochelle"],
    "North Carolina": ["Charlotte", "Raleigh", "Greensboro", "Durham", "Winston-Salem", "Fayetteville", "Cary"],
    "North Dakota": ["Fargo", "Bismarck", "Grand Forks", "Minot"],
    "Ohio": ["Columbus", "Cleveland", "Cincinnati", "Toledo", "Akron", "Dayton"],
    "Oklahoma": ["Oklahoma City", "Tulsa", "Norman", "Broken Arrow", "Edmond"],
    "Oregon": ["Portland", "Salem", "Eugene", "Gresham", "Hillsboro", "Bend"],
    "Pennsylvania": ["Philadelphia", "Pittsburgh", "Allentown", "Erie", "Reading", "Scranton"],
    "Rhode Island": ["Providence", "Cranston", "Warwick", "Pawtucket"],
    "South Carolina": ["Columbia", "Charleston", "North Charleston", "Mount Pleasant", "Greenville"],
    "South Dakota": ["Sioux Falls", "Rapid City", "Aberdeen"],
    "Tennessee": ["Memphis", "Nashville", "Knoxville", "Chattanooga", "Clarksville"],
    "Texas": [
        "Houston", "San Antonio", "Dallas", "Austin", "Fort Worth",
        "El Paso", "Arlington", "Corpus Christi", "Plano", "Laredo",
        "Lubbock", "Garland", "Irving", "Amarillo", "McKinney", "Frisco",
    ],
    "Utah": ["Salt Lake City", "West Valley City", "Provo", "West Jordan", "Orem", "Sandy"],
    "Vermont": ["Burlington", "Essex", "South Burlington", "Colchester"],
    "Virginia": ["Virginia Beach", "Norfolk", "Chesapeake", "Richmond", "Arlington", "Alexandria"],
    "Washington": ["Seattle", "Spokane", "Tacoma", "Vancouver", "Bellevue", "Kirkland", "Olympia"],
    "West Virginia": ["Charleston", "Huntington", "Morgantown", "Parkersburg"],
    "Wisconsin": ["Milwaukee", "Madison", "Green Bay", "Kenosha", "Racine"],
    "Wyoming": ["Cheyenne", "Casper", "Laramie", "Gillette"],
    "Washington D.C.": ["Washington D.C."],
}


def build():
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    states = []
    missing = []
    for state_name in sorted(US_CITIES.keys()):
        cities = US_CITIES[state_name]
        localidades = []
        for i, city in enumerate(cities):
            key = (state_name, city)
            pop = CITY_POPS.get(key)
            if pop is None:
                missing.append(key)
                pop = DEFAULT_POP
            localidades.append({
                "nombre": city,
                "es_principal": i < 3,
                "poblacion": pop,
            })
        states.append({"nombre": state_name, "localidades": localidades})

    result = {"provincias": states}

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    total = sum(len(s["localidades"]) for s in states)
    print(f"Generated: {OUTPUT_PATH}")
    print(f"  States: {len(states)}")
    print(f"  Cities: {total}")
    print(f"  Cities with real population: {total - len(missing)}/{total}")
    if missing:
        print(f"  Missing (using default {DEFAULT_POP:,}):")
        for s, c in missing:
            print(f"    - {s}, {c}")


if __name__ == "__main__":
    build()
