from ib_insync import *
import random
import pandas as pd

# Conectar a IBKR
print("\nConectando a Interactive Brokers...")
ib = IB()
ib.connect('127.0.0.1', 7497, clientId=random.randint(1, 99))

# Pedir tickers
entrada = input("Ingresa tickers separados por coma o escribe 'EXCEL' para leer un archivo: ").strip()

tickers = []

if entrada.upper() == 'EXCEL':
    ruta = input("Ingresa la ruta completa del archivo Excel: ").strip()
    try:
        df = pd.read_excel(ruta)
        # Se asume que la columna de tickers se llama 'Ticker' (puedes cambiarlo)
        if 'Ticker' not in df.columns:
            raise ValueError("El archivo Excel debe tener una columna llamada 'Ticker'")
        tickers = df['Ticker'].dropna().astype(str).str.upper().tolist()
    except Exception as e:
        print("Error al leer el archivo Excel:", e)
        ib.disconnect()
        exit()
else:
    # Separar tickers por coma
    tickers = [t.strip().upper() for t in entrada.split(',') if t.strip()]

if not tickers:
    print("No se ingresaron tickers.")
    ib.disconnect()
    exit()

# Procesar cada ticker
for ticker in tickers:
    print(f"\nProcesando {ticker}...")

    contract = Stock(ticker, 'SMART', 'USD')
    try:
        ib.qualifyContracts(contract)
    except Exception as e:
        print(f"Error al calificar contrato {ticker}: {e}")
        continue

    # Obtener posición
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

    # Generar orden de cierre
    qty = abs(ticker_position.position)
    action = "SELL" if ticker_position.position > 0 else "BUY"

    close_order = MarketOrder(action, qty)
    trade = ib.placeOrder(contract, close_order)
    print(f"Orden enviada para cerrar {ticker} ({action} {qty})")

    ib.sleep(2)
    print("Estado de la orden:", trade.orderStatus.status)

# Desconectar
ib.disconnect()
print("\nProceso finalizado.")
