from ib_insync import *
from ib_insync import util
import random

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
ib.connect("127.0.0.1", port, clientId=random.randint(1, 99))

from ib_insync import Stock, MarketOrder


# -----------------------------
#   HELPERS
# -----------------------------
def _netliq_usd(ib) -> float:
    for r in ib.accountSummary():
        if r.tag == "NetLiquidation" and (r.currency in ("USD", "")):
            return float(r.value)
    for r in ib.accountSummary():
        if r.tag == "NetLiquidation":
            return float(r.value)
    raise RuntimeError("No encontré NetLiquidation.")


def _positions_us_stocks(ib):
    out = []
    for p in ib.positions():
        c = p.contract
        if getattr(c, "secType", None) == "STK" and getattr(c, "currency", None) in ("USD", None, ""):
            if p.position and abs(p.position) > 0:
                out.append(p)
    return out


def _portfolio_items_map(ib) -> dict:
    """
    SYMBOL -> PortfolioItem (incluye marketPrice/marketValue/position/etc.)
    """
    mp = {}
    for it in ib.portfolio():
        sym = getattr(it.contract, "symbol", None)
        if sym:
            mp[sym.upper()] = it
    return mp


def _mktdata_snapshot_map(ib, contracts, timeout_sec: float = 1.2) -> dict:
    """
    Intenta llenar bid/ask/last/change. Si no hay subscripción, vendrá None/0.
    No rompe el script.
    """
    tickers = [ib.reqMktData(c, "", False, False) for c in contracts]

    end = util.time.time() + timeout_sec
    while util.time.time() < end:
        util.sleep(0.2)

    out = {}
    for c, t in zip(contracts, tickers):
        sym = getattr(c, "symbol", None)
        if sym:
            out[sym.upper()] = t
        ib.cancelMktData(c)

    return out


def _fmt(x, nd=2, blank=""):
    if x is None:
        return blank
    try:
        xf = float(x)
    except:
        return blank
    if xf == 0:
        return "0"
    return f"{xf:,.{nd}f}"


def _print_portfolio_table(rows, netliq, title="PORTAFOLIO"):
    print("\n" + "=" * 120)
    print(f"{title}")
    print(f"Net Liquidation Value (USD): {netliq:,.2f}")
    print("=" * 120)
    hdr = (
        f"{'Ticker':<8} {'Bid':>10} {'Ask':>10} {'Last':>10} {'Chg':>10} "
        f"{'Position':>12} {'MktValue':>14} {'Current%':>10} {'Target%':>10}"
    )
    print(hdr)
    print("-" * len(hdr))

    for r in rows:
        print(
            f"{r['symbol']:<8} "
            f"{_fmt(r.get('bid')):>10} {_fmt(r.get('ask')):>10} {_fmt(r.get('last')):>10} {_fmt(r.get('change')):>10} "
            f"{_fmt(r.get('position'), nd=4):>12} {_fmt(r.get('marketValue')):>14} "
            f"{_fmt(r.get('currentPct')):>10} {_fmt(r.get('targetPct')):>10}"
        )
    print("=" * 120)


def build_portfolio_rows(ib, targets: dict | None = None):
    """
    Filas con:
      - Position / MarketValue / Current% desde ib.portfolio()
      - Bid/Ask/Last/Change (best-effort)
      - Target%: igual a Current% excepto overrides
    """
    targets = {k.upper(): float(v) for k, v in (targets or {}).items()}

    netliq = _netliq_usd(ib)
    pos = _positions_us_stocks(ib)

    pmap = _portfolio_items_map(ib)

    contracts = []
    for p in pos:
        sym = p.contract.symbol.upper()
        c = Stock(sym, "SMART", "USD")
        ib.qualifyContracts(c)
        contracts.append(c)

    tmap = _mktdata_snapshot_map(ib, contracts, timeout_sec=1.2) if contracts else {}

    rows = []
    for p in pos:
        sym = p.contract.symbol.upper()

        it = pmap.get(sym)
        if not it:
            continue

        mv = float(getattr(it, "marketValue", 0.0) or 0.0)
        cur_pct = (mv / netliq) * 100 if netliq else 0.0
        tgt_pct = targets.get(sym, cur_pct)

        t = tmap.get(sym)

        rows.append({
            "symbol": sym,
            "bid": getattr(t, "bid", None) if t else None,
            "ask": getattr(t, "ask", None) if t else None,
            "last": getattr(t, "last", None) if t else None,
            "change": getattr(t, "change", None) if t else None,
            "position": float(getattr(it, "position", p.position) or p.position),
            "marketValue": mv,
            "currentPct": cur_pct,
            "targetPct": tgt_pct,
            "contract": Stock(sym, "SMART", "USD"),
            "account": p.account
        })

    rows.sort(key=lambda x: abs(x["marketValue"]), reverse=True)
    return rows, netliq


def parse_targets_input(raw: str) -> dict:
    """
    "LTH 9, AAPL 2.5, TSLA 3" -> {"LTH":9.0, "AAPL":2.5, "TSLA":3.0}
    """
    raw = raw.strip()
    if not raw:
        return {}

    parts = [p.strip() for p in raw.split(",") if p.strip()]
    out = {}
    for p in parts:
        toks = p.split()
        if len(toks) != 2:
            raise ValueError(f"Formato inválido en: '{p}'. Usa: TICKER TARGET% (ej: LTH 9)")
        sym = toks[0].upper().strip()
        tgt = float(toks[1])
        out[sym] = tgt
    return out


def _ref_price_from_portfolio_row(r: dict) -> float | None:
    """
    Precio de referencia derivado:
      marketPrice ≈ |marketValue / position|
    """
    pos = float(r["position"])
    mv = float(r["marketValue"])
    if pos == 0:
        return None
    px = abs(mv / pos)
    return px if px > 0 else None


def simulate_rebalance_orders(rows, netliq, overrides: dict, min_trade_shares=1, sell_first=True):
    """
    Simula rebalance SOLO para overrides:
      - Calcula targetShares usando precio ref de portfolio (mv/pos)
      - Devuelve:
          sim_rows: misma tabla pero con Target% aplicado (solo overrides)
          orders: lista de órdenes propuestas
          sim_effects: dict por símbolo con Position/MV/Current% estimados post-trade
          cash_delta: estimación de cambio de cash (SELL positivo, BUY negativo)
    """
    overrides = {k.upper(): float(v) for k, v in overrides.items()}
    rowmap = {r["symbol"]: r for r in rows}

    # Tabla para mostrar Target%
    sim_rows = []
    for r in rows:
        rr = dict(r)
        if rr["symbol"] in overrides:
            rr["targetPct"] = overrides[rr["symbol"]]
        sim_rows.append(rr)

    orders = []
    sim_effects = {}
    cash_delta = 0.0

    for sym, tgt_pct in overrides.items():
        r = rowmap.get(sym)
        if not r:
            print(f"⚠️  {sym} no está en el portafolio. Se ignora.")
            continue

        px = _ref_price_from_portfolio_row(r)
        if not px:
            print(f"⚠️  {sym} no tiene precio de referencia desde portfolio. Se ignora.")
            continue

        cur_sh = float(r["position"])
        tgt_val = (tgt_pct / 100.0) * netliq

        # Floor para no exceder target (igual que antes)
        tgt_sh = int(tgt_val // px)
        diff = tgt_sh - int(cur_sh)

        # Post-trade estimado
        post_sh = cur_sh + diff
        post_mv = post_sh * px
        post_pct = (post_mv / netliq) * 100 if netliq else 0.0

        sim_effects[sym] = {
            "priceRef": px,
            "preShares": cur_sh,
            "postShares": post_sh,
            "preMarketValue": float(r["marketValue"]),
            "postMarketValue": post_mv,
            "prePct": float(r["currentPct"]),
            "postPct": post_pct,
            "targetPct": tgt_pct,
            "diffShares": diff,
        }

        if abs(diff) >= int(min_trade_shares):
            action = "BUY" if diff > 0 else "SELL"
            qty = abs(diff)
            orders.append((action, qty, sym, Stock(sym, "SMART", "USD"), r["account"]))

            # Cash impact estimado (ejecución a px)
            # SELL -> entra cash (+), BUY -> sale cash (-)
            signed = (qty * px) * (+1 if action == "SELL" else -1)
            cash_delta += signed

    if sell_first:
        orders.sort(key=lambda x: 0 if x[0] == "SELL" else 1)

    return sim_rows, orders, sim_effects, cash_delta


def _print_sim_effects(sim_effects: dict, netliq: float, cash_delta: float):
    """
    Muestra la “foto” estimada post-trade SOLO para los tickers afectados.
    NetLiq estimado: se asume constante; mostramos también cash_delta estimado.
    """
    print("\n" + "=" * 120)
    print("SIMULACIÓN POST-REBALANCE (estimada)")
    print(f"Net Liquidation Value (USD) estimado: {netliq:,.2f}")
    print(f"Cambio estimado de cash por órdenes (SELL + / BUY -): {cash_delta:,.2f} USD")
    print("=" * 120)

    hdr = (
        f"{'Ticker':<8} {'PriceRef':>10} "
        f"{'Pos(pre)':>12} {'Pos(post)':>12} "
        f"{'MV(pre)':>14} {'MV(post)':>14} "
        f"{'Cur%(pre)':>10} {'Cur%(post)':>10} {'Target%':>10} {'DiffSh':>10}"
    )
    print(hdr)
    print("-" * len(hdr))

    for sym in sorted(sim_effects.keys()):
        e = sim_effects[sym]
        print(
            f"{sym:<8} "
            f"{_fmt(e['priceRef']):>10} "
            f"{_fmt(e['preShares'], nd=4):>12} {_fmt(e['postShares'], nd=4):>12} "
            f"{_fmt(e['preMarketValue']):>14} {_fmt(e['postMarketValue']):>14} "
            f"{_fmt(e['prePct']):>10} {_fmt(e['postPct']):>10} "
            f"{_fmt(e['targetPct']):>10} {int(e['diffShares']):>10}"
        )

    print("=" * 120)


def execute_orders(ib, orders, order_type="MKT"):
    trades = []
    for action, qty, sym, contract, account in orders:
        ib.qualifyContracts(contract)
        if order_type.upper() != "MKT":
            raise ValueError("Este script implementa MKT. Se puede extender a LMT.")
        order = MarketOrder(action, qty, account=account)
        trades.append(ib.placeOrder(contract, order))
    util.sleep(1.0)
    return trades


# -----------------------------
# 1) Mostrar portafolio actual
# -----------------------------
rows, netliq = build_portfolio_rows(ib, targets=None)
_print_portfolio_table(rows, netliq, title="PORTAFOLIO ACTUAL")

# -----------------------------
# 2) Preguntar targets
# -----------------------------
print("\nIntroduce Ticker y Target% deseados (solo se rebalanceará lo que indiques).")
print("Formato: TICKER TARGET%, separado por comas.")
print("Ejemplo:  LTH 9, AAPL 2.5, TSLA 3")
raw = input(">>> ").strip()

overrides = parse_targets_input(raw)

if not overrides:
    print("No se ingresaron targets. Saliendo sin cambios.")
else:
    # -----------------------------
    # 3) Simular cómo quedaría + mostrar órdenes + confirmar
    # -----------------------------
    sim_rows, orders, sim_effects, cash_delta = simulate_rebalance_orders(
        rows, netliq, overrides, min_trade_shares=1, sell_first=True
    )

    _print_portfolio_table(sim_rows, netliq, title="PORTAFOLIO (Target% aplicado solo overrides)")

    if not orders:
        print("\n✅ No hay órdenes a ejecutar (ya estás cerca del target o dif es pequeña).")
    else:
        print("\n--- Órdenes propuestas (MKT) ---")
        for action, qty, sym, *_ in orders:
            print(f"{action:4} {qty:>8} {sym} MKT")

        # ✅ NUEVO: mostrar simulación post-trade de tickers afectados + NetLiq
        _print_sim_effects(sim_effects, netliq, cash_delta)

        confirm = input("\n¿Confirmas ejecutar estas órdenes? (YES/NO): ").strip().upper()
        if confirm != "YES":
            print("❌ Cancelado. No se envió nada.")
        else:
            trades = execute_orders(ib, orders, order_type="MKT")
            print("\n✅ Órdenes enviadas. Revisa TWS/Gateway para fills/estado.")

            # refrescar y mostrar nuevamente
            util.sleep(1.0)
            rows2, netliq2 = build_portfolio_rows(ib, targets=overrides)
            _print_portfolio_table(rows2, netliq2, title="PORTAFOLIO (snapshot post-envío)")