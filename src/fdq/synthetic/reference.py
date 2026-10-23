"""Reference lists used to make simulated records look realistic.

Ward names are real wards in each county, but they are only labels: they are
not matched to ward boundaries, so a farmer's ward is not spatially accurate.
"""

TARGET_COUNTIES: list[str] = ["Nakuru", "Kakamega", "Bungoma", "Meru", "Uasin Gishu"]

COUNTY_CODES: dict[str, str] = {
    "Nakuru": "NKR",
    "Kakamega": "KKG",
    "Bungoma": "BGM",
    "Meru": "MRU",
    "Uasin Gishu": "UGS",
}

WARDS: dict[str, list[str]] = {
    "Nakuru": ["Njoro", "Mau Narok", "Molo", "Elburgon", "Subukia", "Solai", "Gilgil", "Mosop"],
    "Kakamega": [
        "Lumakanda",
        "Mautuma",
        "Chevaywa",
        "East Kabras",
        "Butali/Chegulo",
        "Shirere",
        "Sheywe",
        "Mahiakalo",
    ],
    "Bungoma": ["Kimilili", "Kibingei", "Maeni", "Kamukuywa", "Ndivisi", "Mihuu", "Tongaren", "Milima"],
    "Meru": [
        "Timau",
        "Kisima",
        "Kiirua/Naari",
        "Ruiri/Rwarera",
        "Ntima East",
        "Nyaki West",
        "Kianjai",
        "Akithii",
    ],
    "Uasin Gishu": ["Moi's Bridge", "Ziwa", "Soy", "Tapsagoi", "Kamagut", "Moiben", "Tembelio", "Tarakwa"],
}

CROPS: dict[str, list[str]] = {
    "Nakuru": ["maize", "potatoes", "wheat", "beans"],
    "Kakamega": ["maize", "sugarcane", "beans", "tea"],
    "Bungoma": ["maize", "sugarcane", "beans", "coffee"],
    "Meru": ["potatoes", "maize", "coffee", "tea"],
    "Uasin Gishu": ["maize", "wheat", "beans", "potatoes"],
}

FEMALE_FIRST_NAMES: list[str] = [
    "Mary", "Grace", "Jane", "Ann", "Esther", "Lucy", "Faith",
    "Mercy", "Agnes", "Rose", "Caroline", "Beatrice", "Joyce", "Eunice",
]
MALE_FIRST_NAMES: list[str] = [
    "John", "Peter", "Joseph", "David", "James", "Samuel", "Daniel",
    "Paul", "Stephen", "Patrick", "Moses", "Francis", "Geoffrey", "Wilson",
]

_KIKUYU = ["Kamau", "Mwangi", "Njoroge", "Kariuki", "Kimani", "Ndungu", "Njuguna", "Maina", "Gitau", "Waweru"]
_KALENJIN = ["Kiprop", "Kiptoo", "Rotich", "Kosgei", "Cheruiyot", "Kibet", "Korir", "Langat", "Kimutai", "Chepkoech"]
_LUHYA = ["Wafula", "Wekesa", "Barasa", "Simiyu", "Wanjala", "Nyongesa", "Khaemba", "Makokha", "Shikuku", "Masinde"]
_MERU = ["Mwiti", "Kirimi", "Murithi", "Gitonga", "Kinoti", "Mutuma", "Kaimenyi", "Mugambi", "Kiogora", "Mbaabu"]

SURNAMES: dict[str, list[str]] = {
    "Nakuru": _KIKUYU + _KALENJIN,
    "Kakamega": _LUHYA,
    "Bungoma": _LUHYA,
    "Meru": _MERU,
    "Uasin Gishu": _KALENJIN + _LUHYA[:4] + _KIKUYU[:3],
}
