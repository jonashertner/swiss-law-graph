"""The 26 cantons in the order of SR 131.2 and their constitutions (by the title of each
SR entry: 131.211 "Verfassung des Kantons Zürich" … 131.235 "Verfassung der Republik und
des Kantons Jura"). Shared by steps 1, 2, 3, 5, 7 and 8."""

CANTON_CONSTITUTION = {
    "ZH": "131.211", "BE": "131.212", "LU": "131.213", "UR": "131.214", "SZ": "131.215", "OW": "131.216.1",
    "NW": "131.216.2", "GL": "131.217", "ZG": "131.218", "FR": "131.219", "SO": "131.221", "BS": "131.222.1",
    "BL": "131.222.2", "SH": "131.223", "AR": "131.224.1", "AI": "131.224.2", "SG": "131.225", "GR": "131.226",
    "AG": "131.227", "TG": "131.228", "TI": "131.229", "VD": "131.231", "VS": "131.232", "NE": "131.233",
    "GE": "131.234", "JU": "131.235",
}

# A decision is cantonal when its court sits in one of the 26 cantons (OpenCaseLaw's canton column). Every other
# value is a federal or international court and is read as such: CH (federal courts and authorities), CE (ECtHR),
# and since the snapshot of 2026-10-26 EU (CJEU) and UN (UN treaty bodies, ICJ). Before, every value but CH and CE
# counted as a canton, so the CJEU's "AEUV" became a cantonal act "EU AEUV".
CANTONS = tuple(CANTON_CONSTITUTION)
CANTONS_SQL = "(" + ", ".join(f"'{c}'" for c in CANTONS) + ")"
