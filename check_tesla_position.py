from ib_insync import *
import random 
# Conectar Interactive Brokers
print("\nConnecting to Interactive Brokers...")
ib = IB()
ib.connect('127.0.0.1', 7497, clientId=random.randint(1,99))


# Definir el contrato de TSLA
tsla = Stock('TSLA', 'SMART', 'USD')
ib.qualifyContracts(tsla)

# Obtener la posicion actual
positions = ib.positions()

tsla_position = None
for p in positions:
    if p.contract.symbol == "TSLA":
        tsla_position = p
        break

if tsla_position is None:
    print("No tienes una posición abierta en TSLA.")
else:
    print("Posición encontrada:", tsla_position)

# Generar la orden de cierre 
if tsla_position:
    qty = abs(tsla_position.position)

    # Si position > 0 estás largo ⇒ vendes para cerrar
    # Si position < 0 estás corto ⇒ compras para cerrar
    action = "SELL" if tsla_position.position > 0 else "BUY"

    close_order = MarketOrder(action, qty)

    trade = ib.placeOrder(tsla, close_order)
    print("Orden enviada para cerrar TSLA:", trade)

# Confirmar ejecucion 
    ib.sleep(2)  # esperar actualización
print(trade.orderStatus)

