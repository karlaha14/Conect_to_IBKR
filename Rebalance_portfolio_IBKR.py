#------------------------------Importa librerias 
from ib_insync import *
import random
import pandas as pd
import math
import os
from ib_insync import util

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


def _netliq_usd(ib) -> float:
    for r in ib.accountSummary():
        if r.tag == "NetLiquidation" and (r.currency in ("USD", "")):
            return float(r.value)
    for r in ib.accountSummary():
        if r.tag == "NetLiquidation":
            return float(r.value)
    raise RuntimeError("No encontré NetLiquidation.")


def _ref_price_reference(ib, contract) -> float:
    """
    Precio de referencia robusto:
    1) mid realtime (bid/ask)
    2) last realtime
    3) close realtime
    4) mid delayed (delayedBid/Ask)
    5) delayedLast
    6) delayedClose
    """
    ib.qualifyContracts(contract)

    t = ib.reqMktData(contract, "", False, False)
    util.sleep(1.2)

    # realtime
    bid = getattr(t, "bid", None)
    ask = getattr(t, "ask", None)
    last = getattr(t, "last", None)
    close = getattr(t, "close", None)

    # delayed
    d_bid = getattr(t, "delayedBid", None)
    d_ask = getattr(t, "delayedAsk", None)
    d_last = getattr(t, "delayedLast", None)
    d_close = getattr(t, "delayedClose", None)

    ib.cancelMktData(contract)

    # 1) realtime mid
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        return float((bid + ask) / 2)

    # 2) realtime last
    if last is not None and last > 0:
        return float(last)

    # 3) realtime close
    if close is not None and close > 0:
        return float(close)

    # 4) delayed mid
    if d_bid is not None and d_ask is not None and d_bid > 0 and d_ask > 0:
        return float((d_bid + d_ask) / 2)

    # 5) delayed last
    if d_last is not None and d_last > 0:
        return float(d_last)

    # 6) delayed close
    if d_close is not None and d_close > 0:
        return float(d_close)

    raise RuntimeError(
        f"No se pudo obtener precio para {getattr(contract,'symbol','?')} "
        "(ni bid/ask, ni last/close, ni delayed). Revisa market data permissions."
    )


def _positions_us_stocks(ib):
    """Filtra posiciones tipo stock y currency USD (ajusta si tienes otras)."""
    out = []
    for p in ib.positions():
        c = p.contract
        if getattr(c, "secType", None) == "STK" and getattr(c, "currency", None) in ("USD", None, ""):
            if p.position and abs(p.position) > 0:
                out.append(p)
    return out


def current_weights(ib):
    """
    Devuelve:
      - total_value_usd (usando NetLiq como base, al estilo TWS)
      - tabla de posiciones con marketValue y weight%
    """
    base = _netliq_usd(ib)  # como TWS rebalancer (incluye cash)
    pos = _positions_us_stocks(ib)

    rows = []
    for p in pos:
        sym = p.contract.symbol.upper()
        px = _ref_price_reference(ib, p.contract)
        mv = float(p.position) * px
        w = (mv / base) * 100 if base else 0
        rows.append({
            "symbol": sym,
            "position": float(p.position),
            "price": px,
            "marketValue": mv,
            "weightPct": w,
            "contract": p.contract,
            "account": p.account
        })

    rows.sort(key=lambda x: abs(x["marketValue"]), reverse=True)
    return base, rows


def rebalance_from_current(
    ib,
    overrides_target_pct: dict,
    *,
    order_type="MKT",
    min_trade_shares=1,
    sell_first=True
):
    """
    overrides_target_pct: {"LTH": 9}  # target en % (0-100)
    Por defecto: target = current% para todos; se sobreescriben los que indiques.
    Si bajas un target y no subes otros, la diferencia se va a CASH implícitamente.
    """
    base, rows = current_weights(ib)

    # targets = current by default
    targets = {r["symbol"]: r["weightPct"] for r in rows}
    # aplicar overrides
    for k, v in overrides_target_pct.items():
        targets[k.upper()] = float(v)

    # construir plan
    plan = []
    for r in rows:
        sym = r["symbol"]
        tgt_pct = targets.get(sym, r["weightPct"])
        tgt_val = (tgt_pct / 100.0) * base
        tgt_sh = int(tgt_val // r["price"])  # floor para no exceder
        cur_sh = int(r["position"])
        diff = tgt_sh - cur_sh  # + comprar / - vender
        plan.append({**r, "targetPct": tgt_pct, "targetShares": tgt_sh, "diffShares": diff})

    print(f"Base (NetLiq USD): {base:,.2f}\n")
    print("--- Current% vs Target% ---")
    for p in plan:
        if p["symbol"] in {k.upper() for k in overrides_target_pct.keys()}:
            print(
                f"{p['symbol']:6} current={p['weightPct']:6.2f}%  "
                f"target={p['targetPct']:6.2f}%  diffShares={p['diffShares']:>6}"
            )

    # construir órdenes
    orders = []
    for p in plan:
        diff = p["diffShares"]
        if abs(diff) >= min_trade_shares:
            action = "BUY" if diff > 0 else "SELL"
            qty = abs(diff)
            orders.append((action, qty, p["symbol"], p["contract"], p["account"], p["price"], p["weightPct"], p["targetPct"]))

    if not orders:
        print("\n✅ No hay cambios de shares que ejecutar (por redondeo o ya estás en target).")
        return []

    # ordenar: vender primero para liberar margen/cash
    if sell_first:
        orders.sort(key=lambda x: 0 if x[0] == "SELL" else 1)

    print("\n--- Órdenes propuestas (MKT) ---")
    for action, qty, sym, *_ in orders:
        print(f"{action:4} {qty:>6} {sym} {order_type}")

    confirm = input("\n¿Confirmas enviar estas órdenes? (YES/NO): ").strip().upper()
    if confirm != "YES":
        print("❌ Cancelado. No se envió nada.")
        return []

    trades = []
    for action, qty, sym, contract, account, *_ in orders:
        ib.qualifyContracts(contract)
        if order_type.upper() != "MKT":
            raise ValueError("Este helper está en MKT. Se puede extender a LMT.")
        order = MarketOrder(action, qty, account=account)
        trade = ib.placeOrder(contract, order)
        trades.append(trade)

    util.sleep(1.0)
    print("\n✅ Órdenes enviadas. Revisa TWS/Gateway para fills/estado.")
    return trades


# -------------------------
# EJEMPLO: bajar LTH a 9%
# -------------------------
rebalance_from_current(ib, {"LTH": 9})
