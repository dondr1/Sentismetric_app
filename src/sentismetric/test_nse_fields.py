from nse import NSE

with NSE(download_folder="./") as nse:
    sme = nse.listSme()
    print("=== listSme() first entry, all keys/values ===")
    first_company = sme["data"][0]
    for k, v in first_company.items():
        print(f"  {k!r}: {v!r}")

    print()
    print("=== announcements(index='sme') first entry, all keys/values ===")
    anns = nse.announcements(index="sme")
    first_ann = anns[0]
    for k, v in first_ann.items():
        print(f"  {k!r}: {v!r}")