"""Synthetic name pools (Latin transliteration). Names never influence risk."""
from __future__ import annotations

GR_MALE = """Giorgos Dimitris Giannis Nikos Kostas Panagiotis Christos Vasilis Thanasis Michalis
Alexandros Stelios Antonis Manolis Spyros Petros Pavlos Lefteris Stavros Sotiris Argyris Aris
Theodoros Evangelos Fotis Grigoris Haris Ilias Kyriakos Lazaros Marios Nektarios Orestis Periklis
Rigas Savvas Tasos Vangelis Yannis Zacharias Charalambos Andreas Apostolos Dionysis Konstantinos
Nikolaos Ioannis Georgios Dimosthenis Efstathios Miltiadis Philippos Leonidas Alekos Babis Makis
Thodoris Takis Kimon Menelaos Odysseas Pantelis Prodromos Xenofon Triantafyllos Aggelos
Anastasios Athanasios Evripidis Ektoras Filippos Gerasimos Iakovos Lykourgos Napoleon Pericles
Sokratis Telemachos Vlasis Dionisis Haralambos Marinos Kleanthis Nestoras Pandelis Rafail""".split()

GR_FEMALE = """Maria Eleni Katerina Georgia Sofia Dimitra Anna Ioanna Christina Despina Vasiliki
Konstantina Paraskevi Evangelia Angeliki Aikaterini Panagiota Athina Irini Marina Natasa
Nikoletta Olga Pinelopi Rania Stavroula Theodora Zoi Alexandra Antigoni Argyro Artemis Chrysa
Danai Elpida Fotini Galini Ifigeneia Kalliopi Lydia Magda Myrto Nafsika Ourania Roula Sevasti
Tasoula Valentina Voula Xenia Eirini Efthymia Mina Lina Litsa Popi Rena Thalia Aspasia Charikleia
Diamanto Ekaterini Foteini Gianna Hara Ismini Kassiani Lamprini Melina Niki Polyxeni Sotiria
Titika Vicky Zafeiria Agathi Dorothea Evgenia Marianthi Penelope Sevi""".split()

GR_SURNAMES = """Papadopoulos Papadakis Georgiou Ioannou Dimitriou Nikolaou Konstantinou
Papanikolaou Vasileiou Alexiou Michailidis Antoniou Pappas Karagiannis Oikonomou Makris Mitsakis
Galanis Stathopoulos Vlachos Kostopoulos Papageorgiou Theodorou Christodoulou Angelopoulos
Kyriakou Vrettos Zafeiropoulos Anagnostou Triantafyllou Samaras Tsiolis Lazaridis Papaioannou
Giannakopoulos Economou Karamanlis Katsaros Kalogeropoulos Vassilakis Manolakis Petrakis
Stavrakis Psarras Chatzis Chatzidakis Chatzigiannis Sideris Spyropoulos Tzanetakis Kokkinos
Lykos Zervas Drakos Fotiou Gerakis Daskalakis Kapetanakis Kourtidis Ladas Mavridis Nomikos
Orfanos Panagiotopoulos Rousos Sakellariou Tsakiris Voulgaris Xenakis Zografos Argyropoulos
Bakas Bouras Charalampous Diamantis Eleftheriou Floros Gkikas Iliopoulos Kanellopoulos
Laskaris Maniatis Nikitas Pantazis Retsas Skordas Tsouros Vergos Zisis Antonopoulos
Papathanasiou Mpampis Livanos Margaritis Pavlidis Sarris Theofilou Tsamis Valasis Gousis
Alexopoulos Andreadis Athanasiou Bakogiannis Daniil Doukas Evangelou Fragkos Grammenos
Hatzopoulos Kafetzis Kontos Louizos Marinakis Metaxas Panoutsos Rigopoulos Stamatis Tsimas
Vardakis Xydis Zarkadas Kotsis Lambrou Mpekas Nanos Oikonomidis Pitsikalis Roussos""".split()

INTL_MALE = """John Michael David Daniel James Robert Thomas Marco Luca Andrei Mihai Ivan Dmitri
Pavel Jan Tomasz Piotr Hans Peter Stefan Ahmed Omar Ali Besnik Arben Ilir Nikolay Georgi
Viktor Oleksandr Bogdan Yusuf Mehmet Pierre Antoine Carlos Javier Rajesh Amir Fatjon Edmond""".split()

INTL_FEMALE = """Emma Sarah Laura Julia Anna Katarzyna Elena Ioana Maria Olga Natalia Svetlana
Irina Petra Eva Sophie Claire Chiara Giulia Fatima Layla Aisha Elira Albana Valbona Teodora
Desislava Yana Oksana Ayse Elif Camille Isabel Lucia Priya Dina Mirela Alina""".split()

INTL_SURNAMES = """Smith Brown Wilson Taylor Anderson Mueller Schmidt Rossi Ferrari Russo Popescu
Ionescu Dumitru Ivanov Petrov Kowalski Nowak Novak Horvat Hoxha Shehu Kola Berisha Dragan
Georgiev Dimitrov Stoyanov Kovalenko Shevchenko Bondar Yilmaz Kaya Demir Dubois Martin Garcia
Lopez Sanchez Khan Ahmed Singh Patel Kuznetsov Sokolov Mazur Lazar Marin Stan Varga""".split()

EMAIL_PROVIDERS = [
    ("gmail.com", 0.46), ("outlook.com", 0.10), ("hotmail.com", 0.12), ("yahoo.com", 0.10),
    ("yahoo.gr", 0.10), ("icloud.com", 0.08), ("proton.me", 0.04),
]

HANDLES = """bluewave skyrider nightowl sunny greekfire olympus aegean sailor blackcat redfox tiger
sparrow wolfpack pixel seaside cretanman athensfan lucky coolbreeze mountainview nightrider
silverlining oceandrive sunrise moonlight blueberry olivegrove santorini zorbas hellas
fastlane stargazer thunder maverick phoenix falcon dolphin harbor lighthouse windmill""".split()

GR_AREA_CODES = ["210", "231", "2810", "2821", "2410", "2421", "2610", "2641", "2510", "2310"]


def feminize(surname: str) -> str:
    """Greek surnames take a feminine form (Papadopoulos -> Papadopoulou)."""
    for suf, rep in (("opoulos", "opoulou"), ("akis", "aki"), ("idis", "idou"), ("ellis", "elli"),
                     ("os", "ou"), ("as", "a"), ("is", "i"), ("es", "e")):
        if surname.endswith(suf):
            return surname[: -len(suf)] + rep
    return surname
