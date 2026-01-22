from ib_insync import *
import random
import pandas as pd
import certifi
import json
import math
from IPython.display import Image, HTML, display

# Conectar a IBKR
print("\nConectando a Interactive Brokers...")
ib = IB()
ib.connect('127.0.0.1', 7497, clientId=random.randint(1, 99))

#!/usr/bin/env python
try:
    # For Python 3.0 and later
    from urllib.request import urlopen
except ImportError:
    # Fall back to Python 2's urllib2
    from urllib2 import urlopen



# === CONFIGURACION ===
FMP_API_KEY = "gulW74E75O2BjtTbmERXOInaTOD5BltA"  # <- pon aqui tu API key de FMP
TOTAL_INVESTMENT = 10_000
TICKERS = ["WMT", "NFLX", "GOOGL", "KO", "TSLA", "AMZN", "NVDA", "AAPL", "MU", "DIS"]

# === 1. Asignar pesos iguales y mostrar en DataFrame ===
per_ticker_amount = TOTAL_INVESTMENT / len(TICKERS)

df_alloc = pd.DataFrame({
    "ticker": TICKERS,
    "amount_usd": [per_ticker_amount] * len(TICKERS)
})
df_alloc["weight"] = df_alloc["amount_usd"] / TOTAL_INVESTMENT

print("Distribucion inicial (pesos iguales):")
display(df_alloc)

# === 2. Funcion para consultar FMP (endpoint STABLE QUOTE) ===
def get_jsonparsed_data(url):
    response = urlopen(url, cafile=certifi.where())
    data = response.read().decode("utf-8")
    return json.loads(data)

def get_fmp_price(symbol):
    url = (
        f"https://financialmodelingprep.com/stable/quote?"
        f"symbol={symbol}&apikey={FMP_API_KEY}"
    )
    data = get_jsonparsed_data(url)
    # Dependiendo del endpoint puede devolver lista u objeto; manejamos ambos casos:
    if isinstance(data, list):
        data = data[0]
    price = data.get("price")
    if price is None:
        raise ValueError(f"No se pudo obtener 'price' para {symbol}. Respuesta: {data}")
    return float(price)

# Obtener precios actuales
prices = []
for sym in TICKERS:
    try:
        p = get_fmp_price(sym)
    except Exception as e:
        print(f"Error obteniendo precio para {sym}: {e}")
        p = float("nan")
    prices.append(p)

df_prices = pd.DataFrame({
    "ticker": TICKERS,
    "price": prices
})

print("Precios actuales (FMP):")
display(df_prices)

# === 3. Calcular cantidad de acciones (floor) y mostrar en DataFrame ===
df = df_alloc.merge(df_prices, on="ticker", how="left")

df["shares"] = (df["amount_usd"] / df["price"]).apply(
    lambda x: math.floor(x) if pd.notnull(x) else 0
)
df["invested_usd"] = df["shares"] * df["price"]
df["cash_left_usd"] = df["amount_usd"] - df["invested_usd"]

print("Cantidad de acciones a comprar (redondeo floor):")
display(df[["ticker", "price", "amount_usd", "shares", "invested_usd", "cash_left_usd"]])

# === 4. Enviar ordenes a IBKR (confirmacion 'si'/'no') ===
# Aqui uso ib_insync; si ya tienes un objeto 'ib' creado, puedes reutilizarlo y saltarte la conexion.
from ib_insync import IB, Stock, MarketOrder

confirm = input("Deseas ejecutar las ordenes de compra en IBKR? (si/no): ").strip().lower()

if confirm == "si":
    # Conexion a TWS / IB Gateway (ajusta el puerto si usas 7496)
    ib = IB()
    # Cambia puerto=7496 si usas ese
    ib.connect(host="127.0.0.1", port=7497, clientId=1)

    for _, row in df.iterrows():
        ticker = row["ticker"]
        shares = int(row["shares"])

        if shares <= 0 or pd.isnull(row["price"]):
            print(f"Saltando {ticker}: shares={shares} o precio no disponible.")
            continue

        contract = Stock(ticker, "SMART", "USD")
        order = MarketOrder("BUY", shares)

        print(f"Enviando orden: BUY {shares} {ticker}")
        trade = ib.placeOrder(contract, order)

    # Opcional: esperar un poco a que se procesen
    ib.sleep(3)
    ib.disconnect()
    print("Ordenes enviadas a IBKR.")
else:
    print("Transacciones canceladas por el usuario.")

# === 5. Mensaje final ===
print("Proceso finalizado")

