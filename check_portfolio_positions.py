from ib_insync import *
import random 
# Conectar Interactive Brokers
print("\nConnecting to Interactive Brokers...")
ib = IB()
ib.connect('127.0.0.1', 7497, clientId=random.randint(1,99))

# Definir el contrato de los Tickers
nvda = Stock('NVDA', 'SMART', 'USD')
aapl = Stock('APPL', 'SMART', 'USD')
ib.qualifyContracts(nvda, aapl)

# Obtener la posicion actual
positions = ib.positions()

nvda_position = None
for p in positions:
    if p.contract.symbol == "NVDA":
        tsla_position = p
        break

if nvda_position is None:
    print("No tienes una posición abierta en NVDA.")
else:
    print("Posición encontrada:", nvda_position)


aapl_position = None
for p in positions:
    if p.contract.symbol == "AAPL":
        tsla_position = p
        break

if aapl_position is None:
    print("No tienes una posición abierta en AAPL.")
else:
    print("Posición encontrada:", nvda_position)


# Generar la orden de cierre 
if nvda_position:
    qty = abs(nvda_position.position)

    # Si position > 0 estás largo ⇒ vendes para cerrar
    # Si position < 0 estás corto ⇒ compras para cerrar
    action = "SELL" if nvda_position.position > 0 else "BUY"

    close_order = MarketOrder(action, qty)

    trade = ib.placeOrder(nvda, close_order)
    print("Orden enviada para cerrar NVDA:", trade)


if aapl_position:
    qty = abs(aapl_position.position)

    # Si position > 0 estás largo ⇒ vendes para cerrar
    # Si position < 0 estás corto ⇒ compras para cerrar
    action = "SELL" if aapl_position.position > 0 else "BUY"

    close_order = MarketOrder(action, qty)

    trade = ib.placeOrder(aapl, close_order)
    print("Orden enviada para cerrar AAPL:", trade)