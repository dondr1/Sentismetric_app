from bse import BSE

codes_to_check = {
    "INA": "543620",
    "VOEPL": "543597",
    "MODIS": "543539",
    "RMC": "540358",
}

with BSE(download_folder="./") as bse:
    for symbol, code in codes_to_check.items():
        try:
            result = bse.listSecurities(scripcode=code, group="")
            if result:
                print(f"{symbol} ({code}): {result[0]}")
            else:
                print(f"{symbol} ({code}): no result")
        except Exception as e:
            print(f"{symbol} ({code}): failed - {e}")