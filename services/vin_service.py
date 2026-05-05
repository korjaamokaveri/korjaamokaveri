def clean_vehicle_id(value: str) -> str:
    return (value or "").strip().upper().replace(" ", "").replace("-", "")


VIN_WMI_MAKES = {
    # Toyota / Lexus
    "JT": "Toyota", "JTD": "Toyota", "JTE": "Toyota", "JTM": "Toyota", "JTN": "Toyota",
    "2T": "Toyota", "4T": "Toyota", "5T": "Toyota",
    "JTH": "Lexus",

    # Volkswagen Group
    "WVW": "Volkswagen", "WV1": "Volkswagen", "WV2": "Volkswagen",
    "WAU": "Audi", "TRU": "Audi",
    "TMB": "Skoda",
    "VSS": "SEAT",
    "WP0": "Porsche", "WP1": "Porsche",

    # BMW / Mini
    "WBA": "BMW", "WBS": "BMW", "WBX": "BMW",
    "WMW": "Mini",

    # Mercedes-Benz / Smart
    "WDD": "Mercedes-Benz", "WDB": "Mercedes-Benz", "WDC": "Mercedes-Benz",
    "WME": "Smart",

    # Volvo / Polestar
    "YV1": "Volvo", "YV4": "Volvo",
    "LPS": "Polestar",

    # Ford
    "WF0": "Ford", "1F": "Ford", "2F": "Ford", "3F": "Ford",
    "MAJ": "Ford",

    # GM / Opel / Chevrolet
    "W0L": "Opel", "WOL": "Opel",
    "1G": "Chevrolet", "2G": "Chevrolet", "3G": "Chevrolet",
    "KL1": "Chevrolet",

    # Renault / Peugeot / Citroen / DS
    "VF1": "Renault",
    "VF3": "Peugeot",
    "VF7": "Citroën",
    "VR1": "DS",

    # Fiat / Alfa / Lancia / Jeep
    "ZFA": "Fiat",
    "ZAR": "Alfa Romeo",
    "ZLA": "Lancia",
    "1C": "Jeep",

    # Nissan / Infiniti
    "JN1": "Nissan", "JN8": "Nissan", "SJN": "Nissan",
    "JNK": "Infiniti",

    # Honda
    "JH": "Honda", "JHM": "Honda", "SHH": "Honda",
    "2HG": "Honda", "5FN": "Honda",

    # Mazda
    "JMZ": "Mazda", "JM1": "Mazda",

    # Hyundai / Kia
    "KMH": "Hyundai", "TMA": "Hyundai",
    "KNA": "Kia", "U5Y": "Kia",

    # Mitsubishi / Subaru / Suzuki
    "JMB": "Mitsubishi",
    "JF1": "Subaru", "JF2": "Subaru",
    "JS": "Suzuki", "JSA": "Suzuki", "TSM": "Suzuki",

    # Tesla
    "5YJ": "Tesla", "LRW": "Tesla", "XP7": "Tesla",

    # Saab
    "YS3": "Saab",

    # Land Rover / Jaguar
    "SAL": "Land Rover",
    "SAJ": "Jaguar",

    # Dacia
    "UU1": "Dacia",

    # Isuzu
    "JAC": "Isuzu",

    # Iveco
    "ZCFC": "Iveco",

    # MAN / Scania / Volvo Trucks
    "WMA": "MAN",
    "YS2": "Scania",
    "YV2": "Volvo Trucks",
}


def is_vin(value: str) -> bool:
    value = clean_vehicle_id(value)
    if len(value) != 17:
        return False

    forbidden = {"I", "O", "Q"}
    return not any(char in value for char in forbidden)


def detect_make_from_vin(vin: str):
    vin = clean_vehicle_id(vin)

    if not is_vin(vin):
        return None

    for length in (3, 2):
        prefix = vin[:length]
        if prefix in VIN_WMI_MAKES:
            return VIN_WMI_MAKES[prefix]

    return None


def detect_vehicle_identifier(value: str):
    value = clean_vehicle_id(value)

    if is_vin(value):
        return {
            "type": "vin",
            "value": value,
            "detected_make": detect_make_from_vin(value),
        }

    return {
        "type": "plate",
        "value": value,
        "detected_make": None,
    }