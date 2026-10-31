from bse import BSE

with BSE(download_folder='./') as bse:
    securities = bse.listSecurities()

    # Find all distinct segment values
    segments = set(s.get("Segment") for s in securities)
    print("Distinct segments found:", segments)

    # Count how many in each segment
    from collections import Counter
    counts = Counter(s.get("Segment") for s in securities)
    print("Counts per segment:", counts)

    # Show a few SME ones if they exist
    sme_ones = [s for s in securities if s.get("Segment") == "SME"]
    print(f"\nFound {len(sme_ones)} SME securities")
    for s in sme_ones[:5]:
        print(s)

    bse.exit()