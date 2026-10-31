from sentismetric.extract.xbrl import parse_xbrl

facts = parse_xbrl("data/xbrl/NSE/PRITIKA_1178864.xml")
print("revenue entries:", facts.get("revenue"))
