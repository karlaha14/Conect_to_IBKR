from ib_insync import *
import random
import pandas as pd
import certifi
import json
import math
from IPython.display import Image, HTML, display

# === Solicitar PUERTO desde la terminal ===
print("\n¿A qué puerto deseas conectarte?")
print(" - 7496 → Live Trading")
print(" - 7497 → Paper Trading")

while True:
    try:
        port_input = int(input("Ingresa el puerto (7496/7497): ").strip())
        if port_input in (7496, 7497):
            break
        else:
            print("❌ Puerto inválido. Debes ingresar 7496 o 7497.")
    except ValueError:
        print("❌ Entrada inválida. Debes ingresar un número.")

# Conectar a IBKR
print(f"\nConectando a Interactive Brokers en el puerto {port_input}...")
ib = IB()
ib.connect('127.0.0.1', port_input, clientId=random.randint(1, 99))


#!/usr/bin/env python
try:
    # For Python 3.0 and later
    from urllib.request import urlopen
except ImportError:
    from urllib2 import urlopen


# === CONFIGURACION ===
FMP_API_KEY = "gulW74E75O2BjtTbmERXOInaTOD5BltA"
TOTAL_INVESTMENT = 10_000
TICKERS = ["WMT", "NFLX", "GOOGL", "KO", "TSLA", "AMZN", "NVDA", "AAPL", "MU", "DIS"]


# === 1. Asignación igualitaria ===
per_ticker_amount = TOTAL_INVESTMENT / len(TICKERS)

df_alloc = pd.DataFrame({
    "ticker": TICKERS,
    "amount_usd": [per_ticker_amount] * len(TICKERS)
})
df_alloc["weight"] = df_alloc["amount_usd"] / TOTAL_INVESTMENT

print("Distribucion inicial (pesos iguales):")
display(df_alloc)


# === 2. Funciones FMP ===
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
    if isinstance(data, list):
        data = data[0]
    price = data.get("price")
    if price is None:
        raise ValueError(f"No se pudo obtener 'price' para {symbol}. Respuesta: {data}")
    return float(price)


# Obtener precios
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


# === 3. Calcular acciones ===
df = df_alloc.merge(df_prices, on="ticker", how="left")

df["shares"] = (df["amount_usd"] / df["price"]).apply(
    lambda x: math.floor(x) if pd.notnull(x) else 0
)
df["invested_usd"] = df["shares"] * df["price"]
df["cash_left_usd"] = df["amount_usd"] - df["invested_usd"]

print("Cantidad de acciones a comprar (redondeo floor):")
display(df[["ticker", "price", "amount_usd", "shares", "invested_usd", "cash_left_usd"]])


# === 4. Enviar órdenes a IBKR ===
from ib_insync import IB, Stock, MarketOrder

confirm = input("¿Deseas ejecutar las ordenes de compra en IBKR? (si/no): ").strip().lower()

if confirm == "si":
    # Usamos el mismo puerto que el usuario eligió al inicio
    ib = IB()
    ib.connect(host="127.0.0.1", port=port_input, clientId=1)

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

    ib.sleep(3)
    ib.disconnect()
    print("Ordenes enviadas a IBKR.")
else:
    print("Transacciones canceladas por el usuario.")

print("Proceso finalizado")
