#------------------------------Importa librerias 
from ib_insync import *
import random
import pandas as pd
import math

# -----------------------------
#   CONEXIÓN A INTERACTIVE BROKERS
# -----------------------------
# Consulta puerto de conexion
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


# Consulta BUY, SELL or CLOSE
import pandas as pd
from ib_insync import MarketOrder, util

def ask_action() -> str:
    """Pregunta BUY/SELL/CLOSE."""
    while True:
        action = input("¿Qué deseas hacer? (BUY/SELL/CLOSE): ").strip().upper()
        if action in ("BUY", "SELL", "CLOSE"):
            return action
        print("Entrada inválida. Escribe BUY, SELL o CLOSE.")


def load_tickers_from_excel(
    excel_path: str,
    sheet_name: str | int = 0,
    ticker_col: str = "ticker"
) -> list[str]:
    """Lee un Excel y devuelve tickers únicos (mayúsculas)."""
    df = pd.read_excel(excel_path, sheet_name=sheet_name)
    if ticker_col not in df.columns:
        raise ValueError(
            f"No encontré la columna '{ticker_col}'. Columnas disponibles: {list(df.columns)}"
        )
    tickers = (
        df[ticker_col]
        .dropna()
        .astype(str)
        .str.strip()
        .str.upper()
        .tolist()
    )

    seen = set()
    uniq = []
    for t in tickers:
        if t and t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


def choose_ticker_from_list(tickers: list[str], show_n: int = 25) -> str:
    """Filtra y selecciona ticker por texto o número."""
    if not tickers:
        raise ValueError("La lista de tickers está vacía.")

    current = tickers

    while True:
        print("\n--- Selección de ticker desde Excel ---")
        print(f"Tickers cargados: {len(tickers)}")
        print(f"Mostrando hasta {show_n} resultados.")
        print("Opciones: texto=filtrar | número=seleccionar | all=reset | exit=manual\n")

        for i, t in enumerate(current[:show_n], start=1):
            print(f"{i:>3}. {t}")

        q = input("\nBuscar o seleccionar: ").strip()

        if q.lower() == "exit":
            return ""

        if q.lower() == "all":
            current = tickers
            continue

        if q.isdigit():
            idx = int(q)
            if 1 <= idx <= min(len(current), show_n):
                return current[idx - 1]
            print("Número fuera de rango de la lista mostrada.")
            continue

        q_up = q.upper()
        filtered = [t for t in tickers if q_up in t]
        if not filtered:
            print("No encontré coincidencias. Intenta otro filtro o 'all'.")
        else:
            current = filtered


def ask_symbol(
    *,
    excel_path: str | None = None,
    sheet_name: str | int = 0,
    ticker_col: str = "ticker"
) -> str:
    """Ticker manual o desde Excel."""
    while True:
        print("\n¿Cómo quieres ingresar el símbolo?")
        print("  1) Escribir ticker manualmente")
        if excel_path:
            print("  2) Seleccionar desde Excel")

        choice = input("Elige 1" + (" o 2" if excel_path else "") + ": ").strip()

        if choice == "1":
            while True:
                sym = input("Símbolo (ej: AAPL, MSFT, BRK.B): ").strip().upper()
                if sym and all(ch.isalnum() or ch in {".", "-", "_"} for ch in sym):
                    return sym
                print("Símbolo inválido. Intenta de nuevo (sin espacios).")

        if choice == "2" and excel_path:
            try:
                tickers = load_tickers_from_excel(excel_path, sheet_name=sheet_name, ticker_col=ticker_col)
                selected = choose_ticker_from_list(tickers)
                if selected:
                    return selected
                print("Saliendo a ingreso manual...")
            except Exception as e:
                print(f"Error leyendo/seleccionando desde Excel: {e}")
            continue

        print("Opción inválida.")


def ask_order_type() -> str:
    while True:
        otype = input("Tipo de orden (MKT/LMT) [MKT]: ").strip().upper()
        if otype == "":
            return "MKT"
        if otype in ("MKT", "LMT"):
            return otype
        print("Entrada inválida. Escribe MKT o LMT.")


def ask_limit_price() -> float:
    while True:
        raw = input("Precio límite (ej: 195.50): ").strip()
        try:
            px = float(raw)
            if px > 0:
                return px
        except ValueError:
            pass
        print("Precio inválido. Debe ser un número > 0.")


# -------------------------
# PRICING + QTY (SHARES or USD)
# -------------------------
def _get_reference_price(ib, contract) -> float:
    """
    Obtiene un precio de referencia (mid si hay bid/ask, sino last).
    Usa snapshot (reqMktData) y espera un momento.
    """
    ib.qualifyContracts(contract)

    ticker = ib.reqMktData(contract, "", False, False)
    util.sleep(1.0)  # espera a que llegue data

    bid = getattr(ticker, "bid", None)
    ask = getattr(ticker, "ask", None)
    last = getattr(ticker, "last", None)
    close = getattr(ticker, "close", None)

    # mid > last > close
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        px = (bid + ask) / 2
    elif last is not None and last > 0:
        px = last
    elif close is not None and close > 0:
        px = close
    else:
        raise RuntimeError("No se pudo obtener precio (bid/ask/last/close). Revisa market data permissions.")

    ib.cancelMktData(contract)
    return float(px)


def ask_qty_mode() -> str:
    """
    'SHARES' o 'USD'
    """
    while True:
        mode = input("¿Cómo quieres definir el tamaño? (SHARES/USD): ").strip().upper()
        if mode in ("SHARES", "USD"):
            return mode
        print("Entrada inválida. Escribe SHARES o USD.")


def ask_shares() -> float:
    while True:
        raw = input("Cantidad de acciones (ej: 1, 10, 100): ").strip()
        try:
            qty = float(raw)
            if qty > 0:
                return qty
        except ValueError:
            pass
        print("Cantidad inválida. Debe ser un número > 0.")


def ask_usd_amount() -> float:
    while True:
        raw = input("Monto en USD (ej: 500, 2500): ").strip()
        try:
            amt = float(raw)
            if amt > 0:
                return amt
        except ValueError:
            pass
        print("Monto inválido. Debe ser un número > 0.")


def compute_shares_from_usd(usd_amount: float, ref_price: float) -> int:
    """
    Convierte USD → shares usando precio de referencia.
    Redondea hacia abajo para no exceder el monto.
    """
    shares = int(usd_amount // ref_price)
    if shares <= 0:
        raise ValueError(f"El monto ${usd_amount:g} es demasiado bajo para el precio {ref_price:g}.")
    return shares


# -------------------------
# CLOSE POSITIONS (MKT)
# -------------------------
def _positions_open(ib):
    return [p for p in ib.positions() if p.position and abs(p.position) > 0]


def _describe_position(p) -> str:
    c = p.contract
    sym = getattr(c, "symbol", "?")
    sec = getattr(c, "secType", "?")
    exch = getattr(c, "exchange", "?")
    cur = getattr(c, "currency", "?")
    qty = p.position
    avg = p.avgCost
    return f"{sym} | {sec} | {exch} | {cur} | qty={qty:g} | avgCost={avg:g}"


def close_positions_mkt(ib):
    """
    Interactivo:
    - lista posiciones abiertas
    - eliges una o todas
    - elige cerrar FULL (100%) o PARTIAL (por shares o USD)
    - confirmación
    - envía MKT opuesta
    """
    pos = _positions_open(ib)
    if not pos:
        print("✅ No hay posiciones abiertas para cerrar.")
        return []

    print("\n--- Posiciones abiertas ---")
    for i, p in enumerate(pos, start=1):
        print(f"{i:>3}. {_describe_position(p)}")

    print("\nOpciones:")
    print("  - Número para cerrar esa posición")
    print("  - ALL para cerrar todas")
    print("  - EXIT para cancelar")

    choice = input("\n¿Qué deseas cerrar?: ").strip().upper()
    if choice == "EXIT":
        print("Cancelado.")
        return []

    if choice == "ALL":
        selected = pos
    elif choice.isdigit():
        idx = int(choice)
        if idx < 1 or idx > len(pos):
            print("Número fuera de rango. Cancelado.")
            return []
        selected = [pos[idx - 1]]
    else:
        print("Entrada inválida. Cancelado.")
        return []

    # FULL vs PARTIAL
    mode_close = input("\n¿Cerrar FULL (100%) o PARTIAL? [FULL]: ").strip().upper() or "FULL"
    if mode_close not in ("FULL", "PARTIAL"):
        print("Entrada inválida. Cancelado.")
        return []

    orders_to_send = []

    for p in selected:
        c = p.contract
        pos_qty = float(p.position)
        action = "SELL" if pos_qty > 0 else "BUY"
        max_qty_to_close = abs(pos_qty)

        close_qty = max_qty_to_close  # FULL por defecto

        if mode_close == "PARTIAL":
            qty_mode = ask_qty_mode()
            if qty_mode == "SHARES":
                partial = ask_shares()
                close_qty = min(partial, max_qty_to_close)
            else:  # USD
                # Para USD necesitamos precio de referencia del contract
                try:
                    ref_px = _get_reference_price(ib, c)
                    usd_amt = ask_usd_amount()
                    calc_sh = compute_shares_from_usd(usd_amt, ref_px)
                    close_qty = min(calc_sh, int(max_qty_to_close))
                except Exception as e:
                    print(f"No se pudo calcular cierre por USD para {getattr(c,'symbol','?')}: {e}")
                    continue

            if close_qty <= 0:
                continue

        orders_to_send.append((c, action, close_qty, p.account))

    if not orders_to_send:
        print("No hay órdenes a enviar.")
        return []

    print("\n--- Resumen de cierre (MKT) ---")
    for c, action, close_qty, acc in orders_to_send:
        sym = getattr(c, "symbol", "?")
        sec = getattr(c, "secType", "?")
        print(f"{acc}: {action} {close_qty:g} {sym} ({sec}) MKT")

    confirm = input("\n¿Confirmas enviar estas órdenes? (YES/NO): ").strip().upper()
    if confirm != "YES":
        print("❌ No confirmado. No se envió nada.")
        return []

    trades = []
    for c, action, close_qty, acc in orders_to_send:
        ib.qualifyContracts(c)
        order = MarketOrder(action, close_qty, account=acc)
        trade = ib.placeOrder(c, order)
        trades.append(trade)

    util.sleep(1.0)
    print("✅ Órdenes enviadas. Revisa TWS/Gateway (Paper) para confirmar fills/estado.")
    return trades


# -------------------------
# MAIN FLOW
# -------------------------
# Configura esto para habilitar selección por Excel:
# excel_path = r"C:\Users\HP\Documents\tickers.xlsx"
excel_path = r"C:\Users\HP\Documents\Conect IBKR, Visual Code\Testing_Close_tickers.xlsx"
sheet_name = 0
ticker_col = "Ticker"

action = ask_action()

if action == "CLOSE":
    close_positions_mkt(ib)

else:
    # BUY / SELL
    symbol = ask_symbol(excel_path=excel_path, sheet_name=sheet_name, ticker_col=ticker_col)

    # Contrato (MVP: acciones US SMART/USD)
    contract = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(contract)

    qty_mode = ask_qty_mode()
    if qty_mode == "SHARES":
        qty = ask_shares()
        ref_px = None
    else:
        usd_amt = ask_usd_amount()
        ref_px = _get_reference_price(ib, contract)
        qty = compute_shares_from_usd(usd_amt, ref_px)
        print(f"Precio ref usado: {ref_px:g}  →  shares calculadas: {qty}")

    order_type = ask_order_type()
    limit_price = None
    if order_type == "LMT":
        limit_price = ask_limit_price()

    print("\n--- Resumen de orden ---")
    if qty_mode == "USD":
        print(f"Monto objetivo: ${usd_amt:g} | precio ref: {ref_px:g} | shares: {qty}")
    if order_type == "MKT":
        print(f"{action} {qty:g} {symbol} MKT")
    else:
        print(f"{action} {qty:g} {symbol} LMT @ {limit_price:g}")

    confirm = input("\n¿Confirmas enviar esta orden? (YES/NO): ").strip().upper()
    if confirm != "YES":
        print("❌ No confirmado. No se envió nada.")
    else:
        if order_type == "MKT":
            order = MarketOrder(action, qty)
        else:
            order = LimitOrder(action, qty, limit_price)

        trade = ib.placeOrder(contract, order)
        util.sleep(1.0)
        print("✅ Orden enviada. Trade object:", trade)

