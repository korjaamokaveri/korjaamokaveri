def build_dtc_enrichment(item):
    code = (item["code"] or "").upper()
    title = item["title"] or ""
    desc = item["description"] or ""

    text = f"{code} {title} {desc}".lower()

    causes = []
    symptoms = []
    steps = []

    if "sytytyskatkos" in text or "misfire" in text:
        symptoms = "Moottori voi käydä epätasaisesti, nykiä, täristä tyhjäkäynnillä tai menettää tehoa."
        causes = [
            "Sytytystulppa kulunut tai viallinen",
            "Sytytyspuola viallinen",
            "Polttoainesuutin tukossa tai viallinen",
            "Imuvuoto tai seosvika",
        ]
        steps = [
            "Lue vikakoodit ja freeze frame -tiedot.",
            "Tarkista sytytystulpan kunto.",
            "Vaihda puolaa sylinterien välillä ja seuraa siirtyykö vika.",
            "Tarkista suuttimen toiminta.",
            "Tarkista imuvuodot ja polttoainepaine.",
        ]
    elif "laiha" in text or "lean" in text:
        symptoms = "Moottori voi nykiä, käydä laihalla, kuluttaa epätasaisesti tai antaa seoskorjausarvoihin liittyviä oireita."
        causes = [
            "Imuvuoto",
            "Likainen tai viallinen ilmamassamittari",
            "Matala polttoainepaine",
            "Viallinen happitunnistin",
        ]
        steps = [
            "Tarkista imuvuodot savukoneella tai visuaalisesti.",
            "Tarkista MAF-anturin lukemat testerillä.",
            "Mittaa polttoainepaine.",
            "Tarkista lambda-/A/F-anturin toiminta.",
        ]
    elif "rikas" in text or "rich" in text:
        symptoms = "Moottori voi kuluttaa paljon, haista polttoaineelle, käydä raskaasti tai savuttaa."
        causes = [
            "Vuotava suutin",
            "Viallinen MAF-anturi",
            "Liian korkea polttoainepaine",
            "Virheellinen happitunnistimen signaali",
        ]
        steps = [
            "Tarkista polttoainepaine.",
            "Tarkista suuttimien vuodot.",
            "Tarkista MAF-anturin lukemat.",
            "Tarkista lambda-/A/F-anturin signaali.",
        ]
    elif "paine" in text or "pressure" in text:
        symptoms = "Ajoneuvossa voi esiintyä tehonpuutetta, käynnistysvaikeutta tai häiriövalon syttymistä."
        causes = [
            "Paineanturi viallinen",
            "Johtosarja tai liitin viallinen",
            "Pumppu ei tuota oikeaa painetta",
            "Suodatin tai kanava tukossa",
        ]
        steps = [
            "Tarkista liittimet ja johdot.",
            "Vertaa painearvoa testerillä todelliseen mittaukseen.",
            "Mittaa anturin syöttöjännite ja maa.",
            "Tarkista pumpun toiminta ja mahdolliset tukokset.",
        ]
    else:
        symptoms = "Oireet riippuvat järjestelmästä. Tyypillisiä oireita ovat vikavalon syttyminen, tehonpuute tai epänormaali toiminta."
        causes = [
            "Johtosarja tai liitin viallinen",
            "Anturi tai toimilaite viallinen",
            "Virransyöttö tai maadoitus puutteellinen",
            "Ohjainlaitevika mahdollinen",
        ]
        steps = [
            "Lue kaikki vikakoodit ja freeze frame -tiedot.",
            "Tarkista liittimet ja johdot silmämääräisesti.",
            "Tarkista virransyöttö ja maadoitus.",
            "Testaa epäilty komponentti valmistajan ohjearvojen mukaan.",
            "Poista vikakoodi ja tee koeajo.",
        ]

    return {
        "title": title,
        "description": desc,
        "problem_symptoms": symptoms,
        "causes": "\n".join(causes),
        "steps": "\n".join(steps),
        "admin_note": f"Paikallisen AI-rikastuksen ehdotus koodille {code}. Tarkista ennen hyväksyntää.",
    }