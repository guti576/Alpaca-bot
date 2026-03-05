import asyncio
import pandas as pd
import os
import csv
from datetime import datetime, timezone, timedelta

# Importaciones específicas de STOCKS
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.live import StockDataStream

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass


# ---------------------------------------------------------
# FUNCIONES DE LOG
# ---------------------------------------------------------
def log_to_csv(data_dict, CSV_FILENAME):
    """Guarda eventos en CSV"""
    file_exists = os.path.isfile(CSV_FILENAME)
    fieldnames = ['utc_time', 'symbol', 'action', 'price', 'details']
    try:
        with open(CSV_FILENAME, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists: writer.writeheader()
            writer.writerow(data_dict)
            print(f"--> [LOG] {data_dict['action']}")
    except Exception as e:
        print(f"Error CSV: {e}")


# ---------------------------------------------------------
# FUNCIONES DE DATOS
# ---------------------------------------------------------
def get_historical_data(data_client, symbol, TIMEFRAME_STRATEGY):
    # Pedimos 20 días para asegurar el cálculo correcto de la EMA 200
    start_time = datetime.now(timezone.utc) - timedelta(days=50)
    req = StockBarsRequest(symbol_or_symbols=[symbol], timeframe=TIMEFRAME_STRATEGY, start=start_time, limit=1000)
    bars = data_client.get_stock_bars(req)
    df = bars.df
    if isinstance(df.index, pd.MultiIndex): df = df.reset_index(level=0, drop=True)
    
    # Flag de cierre (adaptado)
    now_utc = datetime.now(timezone.utc)
    candle_starts = df.index.to_pydatetime()
    df['is_closed'] = [now_utc >= (t + timedelta(hours=1, seconds=1)) for t in candle_starts]
    return df


# ---------------------------------------------------------
# FUNCIONES DE COMPRA
# ---------------------------------------------------------
def put_bracket_order(trading_client, symbol, df, USD_PER_TRADE, TAKE_PROFIT_PCT = 1.04, STOP_LOSS_PCT = 0.98):
    # 1. Comprobar si ya tenemos posición
    try:
        trading_client.get_open_position(symbol)
        print(f"[{symbol}] Posición existente. Saltando ejecución.")
        return False # Ya estamos dentro, no compramos
    except:
        pass # No hay posición, procedemos

    # 2. Calcular cantidad de acciones
    # Nota: Asegúrate de que tu DataFrame tiene la columna en minúscula 'close' o cámbiala a 'Close' si usas yfinance
    current_price = df.iloc[-1]['close'] if 'close' in df.columns else df.iloc[-1]['Close']
    qty = int(USD_PER_TRADE // current_price) 
    
    if qty <= 0:
        print(f"[{symbol}] Fondos insuficientes ({USD_PER_TRADE}$) para comprar 1 acción a {current_price:.2f}$.")
        return False # No hay dinero suficiente para 1 acción entera

    # 3. Calcular niveles de SL y TP
    tp_price = round(current_price * TAKE_PROFIT_PCT, 2)
    sl_price = round(current_price * STOP_LOSS_PCT, 2)
        
    print(f"✅ SEÑAL DE COMPRA: {symbol} a {current_price:.2f}$")
    print(f"   Configurando Bracket: TP @ {tp_price}$ | SL @ {sl_price}$ | Cantidad: {qty}")
        
    # 4. Crear ORDEN BRACKET
    req = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.GTC,
        order_class=OrderClass.BRACKET,
        take_profit=TakeProfitRequest(limit_price=tp_price),
        stop_loss=StopLossRequest(stop_price=sl_price)
    )
    
    # 5. Enviar orden con manejo de errores
    try:
        trading_client.submit_order(req)
        print(f"🚀 Orden ejecutada con éxito para {symbol}.")
        return True # Todo salió perfecto
    except Exception as e:
        print(f"❌ Error de la API de Alpaca al enviar la orden para {symbol}: {e}")
        return False # Falló el envío de la orden