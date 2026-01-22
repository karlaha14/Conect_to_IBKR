from ib_insync import *
import random
import pandas as pd

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

    # -----------------------------
    #   INPUT PARA DEFINIR CANTIDAD DE CIERRE
    # -----------------------------
    while True:
        qty_input = input(
            f"Ingrese cantidad a cerrar para {ticker} (0 = cerrar completa, posición actual = {current_qty}): "
        ).strip()

        try:
            # Se permite entero, 1 decimal o 3 decimales
            if qty_input.count('.') in (0, 1):
                qty = float(qty_input)
            else:
                raise ValueError

            if qty < 0:
                print("⚠️  No se permiten cantidades negativas.")
                continue

            break

        except:
            print("⚠️  Ingresa un número válido. Ejemplos: 0, 10, 10.5, 10.125")

    # Si el usuario quiere cerrar completa
    if qty == 0:
        qty_to_close = current_qty
    else:
        qty_to_close = min(qty, current_qty)  # No exceder posición

    action = "SELL" if ticker_position.position > 0 else "BUY"

    # -----------------------------
    #   COLOCAR ORDEN
    # -----------------------------
    print(f"Enviando orden {action} {qty_to_close} de {ticker}...")

    close_order = MarketOrder(action, qty_to_close)
    trade = ib.placeOrder(contract, close_order)

    ib.sleep(2)
    print("Estado de la orden:", trade.orderStatus.status)

# -----------------------------
#   DESCONECTAR
# -----------------------------
ib.disconnect()
print("\nProceso finalizado.")

