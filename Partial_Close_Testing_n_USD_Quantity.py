from ib_insync import *
import random
import pandas as pd
import math

# -----------------------------
#   CONEXIÓN A INTERACTIVE BROKERS
# -----------------------------
print("\nConectando a Interactive Brokers...")

while True:
    try:
        port = int(input("Ingresa 7497 (paper) o 7496 (live): ").strip())
        if port in (7496, 7497):
            break
        else:
            print("⚠️  Solo se permite 7496 o 7497.")
    except:
        print("⚠️  Entrada inválida.")

ib = IB()
ib.connect('127.0.0.1', port, clientId=random.randint(1, 99))

# -----------------------------
#   LECTURA DE TICKERS
# -----------------------------
entrada = input("\nIngresa tickers separados por coma o escribe 'EXCEL' para leer un archivo: ").strip()
tickers = []

if entrada.upper() == 'EXCEL':
    ruta = input("Ingresa la ruta completa del archivo Excel: ").strip()
    try:
        df = pd.read_excel(ruta)

        if 'Ticker' not in df.columns:
            raise ValueError("El archivo Excel debe tener una columna llamada 'Ticker'")

        tickers = df['Ticker'].dropna().astype(str).str.upper().tolist()
    except Exception as e:
        print("Error al leer el archivo Excel:", e)
        ib.disconnect()
        exit()

else:
    tickers = [t.strip().upper() for t in entrada.split(',') if t.strip()]

if not tickers:
    print("No se ingresaron tickers.")
    ib.disconnect()
    exit()

# -----------------------------
#   PROCESAR CADA TICKER
# -----------------------------
for ticker in tickers:
    print(f"\nProcesando {ticker}...")

    contract = Stock(ticker, 'SMART', 'USD')
    try:
        ib.qualifyContracts(contract)
    except Exception as e:
        print(f"Error al calificar contrato {ticker}: {e}")
        continue

    # Obtener posiciones abiertas
    positions = ib.positions()
    ticker_position = None

    for p in positions:
        if p.contract.symbol.upper() == ticker:
            ticker_position = p
            break

    if not ticker_position:
        print(f"No tienes posición abierta en {ticker}.")
        continue

    print("Posición encontrada:", ticker_position)

    current_qty = abs(ticker_position.position)

    # ------------------------------------------------------
    #  Elegir modo: cerrar por acciones o por monto en USD
    # ------------------------------------------------------
    print("\n¿Deseas cerrar por:")
    print("1 = Cantidad de acciones")
    print("2 = Monto en USD")

    while True:
        modo = input("Elige (1 o 2): ").strip()
        if modo in ("1", "2"):
            break
        print("⚠️ Ingresa 1 o 2.")

    # ------------------------------------------------------
    #   MODO 1: CERRAR POR # DE ACCIONES
    # ------------------------------------------------------
    if modo == "1":
        while True:
            qty_input = input(
                f"Ingrese cantidad a cerrar para {ticker} (0 = cerrar completa, posición actual = {current_qty}): "
            ).strip()

            try:
                qty = float(qty_input)
                if qty < 0:
                    print("⚠️ No se permiten cantidades negativas.")
                    continue
                break

            except:
                print("⚠️ Ingresa un número válido. Ejemplos: 0, 10, 10.5, 10.125")

        if qty == 0:
            qty_to_close = current_qty
        else:
            qty_to_close = min(qty, current_qty)

    # ------------------------------------------------------
    #   MODO 2: CERRAR POR USD (redondeo hacia abajo)
    # ------------------------------------------------------
    else:
        print("\nSolicitando precio de mercado actual...")
        ticker_data = ib.reqMktData(contract, "", False, False)

        ib.sleep(1.5)

        price_candidates = [ticker_data.last, ticker_data.close]
        price_candidates = [
            p for p in price_candidates
            if p is not None and not math.isnan(p) and p > 0
        ]

        if not price_candidates:
            print("⚠️ No se pudo obtener un precio válido. Saltando este ticker.")
            continue

        price = price_candidates[0]
        print(f"Precio actual: {price} USD")

        while True:
            usd_input = input("Ingrese monto en USD a cerrar (0 = cerrar completa): ").strip()
            try:
                usd_value = float(usd_input)
                if usd_value < 0:
                    print("⚠️ No se permiten valores negativos.")
                    continue
                break
            except:
                print("⚠️ Ingresa un valor en USD válido.")

        if usd_value == 0:
            qty_to_close = current_qty
        else:
            raw_qty = usd_value / price
            qty_to_close = math.floor(raw_qty)
            qty_to_close = min(qty_to_close, current_qty)

        if qty_to_close <= 0:
            print("⚠️ La cantidad equivalente quedó en 0 acciones. No se enviará orden.")
            continue

        print(f"Cantidad equivalente redondeada a cerrar: {qty_to_close} acciones")

    # -----------------------------
    #   COLOCAR ORDEN
    # -----------------------------
    action = "SELL" if ticker_position.position > 0 else "BUY"

    print(f"\nEnviando orden {action} {qty_to_close} de {ticker}...")

    close_order = MarketOrder(action, qty_to_close)
    trade = ib.placeOrder(contract, close_order)

    ib.sleep(2)
    print("Estado de la orden:", trade.orderStatus.status)

# -----------------------------
#   DESCONECTAR
# -----------------------------
ib.disconnect()
print("\nProceso finalizado.")
