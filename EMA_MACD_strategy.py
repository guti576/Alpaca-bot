import asyncio
import pandas as pd
import os
import csv
import math
import logging
import sys
from datetime import datetime, timezone, timedelta
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.live import CryptoDataStream
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# --- CONFIGURACIÓN DE LOGGING (Console Output) ---
# Esto hace que cada mensaje tenga TIMESTAMP automático
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger()

# --- CONFIGURACIÓN DEL BOT ---
API_KEY = "PK2CNGKUVBXK5XM75N64PIQIRL"
SECRET_KEY = "G1Ag2nzs6cFosZvBRp1QKTFLvw5nYBvNidn1W8Em9zNE"
BASE_URL = 'https://paper-api.alpaca.markets'
CSV_FILENAME = './log/historial_operaciones.csv'

SYMBOLS = ['BTC/USD', 'ETH/USD', 'SOL/USD']
TIMEFRAME_STRATEGY = TimeFrame.Hour
USD_PER_TRADE = 1000.0 

# Clientes
trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)
data_client = CryptoHistoricalDataClient()
stream_client = CryptoDataStream(API_KEY, SECRET_KEY)

# Control de hora
last_processed_hour = {}

def calculate_qty(symbol, price):
    raw_qty = USD_PER_TRADE / price
    if 'BTC' in symbol: return round(raw_qty, 6)
    elif 'ETH' in symbol: return round(raw_qty, 5)
    else: return round(raw_qty, 2)

def log_to_csv(data_dict):
    """Guarda la decisión final en CSV"""
    file_exists = os.path.isfile(CSV_FILENAME)
    fieldnames = [
        'candle_time', 'processed_at', 'delay_sec', 
        'symbol', 'close', 'qty_bought', 'usd_invested', 
        'decision', 'details'
    ]
    try:
        with open(CSV_FILENAME, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists: writer.writeheader()
            writer.writerow(data_dict)
            logger.info(f"CSV actualizado: {data_dict['decision']} para {data_dict['symbol']}")
    except Exception as e:
        logger.error(f"Error escribiendo CSV: {e}")

def get_historical_data(symbol):
    logger.info(f"[{symbol}] Descargando historial oficial de 1H...")
    req = CryptoBarsRequest(
        symbol_or_symbols=[symbol],
        timeframe=TIMEFRAME_STRATEGY,
        limit=250 
    )
    bars = data_client.get_crypto_bars(req)
    return bars.df

def calculate_indicators(df):
    if isinstance(df.index, pd.MultiIndex):
        df = df.reset_index(level=0, drop=True)
        
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    k = df['close'].ewm(span=12, adjust=False).mean()
    d = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = k - d
    df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    return df

def analyze_and_execute(symbol, df):
    if len(df) < 200: 
        logger.warning(f"[{symbol}] Datos insuficientes ({len(df)} velas). Esperando más historia.")
        return

    # Tiempos
    now_utc = datetime.now(timezone.utc)
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    candle_start = curr.name.to_pydatetime()
    candle_close = candle_start + timedelta(hours=1)
    delay = (now_utc - candle_close).total_seconds()

    # Log detallado de la situación técnica
    logger.info(f"--- ANÁLISIS TÉCNICO {symbol} ---")
    logger.info(f"Precio: {curr['close']:.2f} | EMA200: {curr['ema200']:.2f}")
    logger.info(f"MACD Actual: {curr['macd']:.4f} | Signal Actual: {curr['signal']:.4f}")
    logger.info(f"MACD Previo: {prev['macd']:.4f} | Signal Previo: {prev['signal']:.4f}")

    # Lógica
    is_uptrend = curr['close'] > curr['ema200']
    macd_crossover = (prev['macd'] < prev['signal']) and (curr['macd'] > curr['signal'])
    is_pullback = curr['macd'] < 0

    # Logging intermedio de condiciones
    if not is_uptrend: logger.info(f"CONDICIÓN FALLIDA: Tendencia bajista (Precio < EMA).")
    if not macd_crossover: logger.info(f"CONDICIÓN FALLIDA: No hay cruce alcista MACD.")
    if not is_pullback: logger.info(f"CONDICIÓN FALLIDA: El cruce no es bajo cero (Pullback).")

    # Preparar objeto log
    log_entry = {
        'candle_time': candle_start,
        'processed_at': now_utc.strftime('%H:%M:%S'),
        'delay_sec': round(delay, 2),
        'symbol': symbol,
        'close': round(curr['close'], 2),
        'qty_bought': 0, 'usd_invested': 0,
        'decision': 'WAIT', 'details': '-'
    }

    if is_uptrend and macd_crossover and is_pullback:
        logger.info(f"¡SEÑAL ENCONTRADA EN {symbol}! Verificando cartera...")
        
        has_position = False
        try:
            positions = trading_client.get_all_positions()
            for p in positions:
                if p.symbol == symbol.replace('/', ''):
                    has_position = True
                    break
        except Exception as e: logger.error(f"Error API Alpaca: {e}")

        if has_position:
            logger.warning(f"Señal ignorada: Ya tienes {symbol} en cartera.")
            log_entry['decision'] = 'SKIPPED'
            log_entry['details'] = 'Posicion ya abierta'
        else:
            try:
                price = curr['close']
                qty = calculate_qty(symbol, price)
                
                # Ejecución
                req = MarketOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.GTC,
                    take_profit=TakeProfitRequest(limit_price=price * 1.04),
                    stop_loss=StopLossRequest(stop_price=price * 0.98)
                )
                logger.info(f"Enviando orden de compra por {qty} {symbol}...")
                order = trading_client.submit_order(req)
                
                log_entry['decision'] = 'BUY_EXECUTED'
                log_entry['qty_bought'] = qty
                log_entry['usd_invested'] = round(qty * price, 2)
                log_entry['details'] = f"ID: {order.id}"
                logger.info(f"ORDEN COMPLETADA: {order.id}")
                
            except Exception as e:
                logger.error(f"FALLO AL COMPRAR: {e}")
                log_entry['decision'] = 'ERROR'
                log_entry['details'] = str(e)
    else:
        logger.info(f"Decisión: ESPERAR (No se cumplen todas las condiciones)")
        reasons = []
        if not is_uptrend: reasons.append("Bajista")
        if not macd_crossover: reasons.append("No Cruce")
        if not is_pullback: reasons.append("MACD>0")
        log_entry['details'] = "/".join(reasons)

    log_to_csv(log_entry)

async def bar_handler(data):
    symbol = data.symbol
    current_timestamp = data.timestamp
    current_hour = current_timestamp.hour
    current_minute = current_timestamp.minute

    # Chequeo de estado
    if symbol not in last_processed_hour:
        last_processed_hour[symbol] = -1

    # Lógica de detección de cambio de hora
    if last_processed_hour[symbol] != current_hour:
        logger.info(f"========================================")
        logger.info(f"NUEVA VELA DE HORA DETECTADA: {current_hour}:00 para {symbol}")
        logger.info(f"Trigger recibido a las: {current_timestamp}")
        
        last_processed_hour[symbol] = current_hour
        try:
            df = get_historical_data(symbol)
            df = calculate_indicators(df)
            analyze_and_execute(symbol, df)
        except Exception as e:
            logger.error(f"Excepción crítica procesando {symbol}: {e}")
        logger.info(f"Fin del proceso para {symbol}. Volviendo a escucha...")
        logger.info(f"========================================")
        
    else:
        # ESTA ES LA PARTE QUE TE MUESTRA QUE EL BOT ESTÁ VIVO
        # Muestra un log cada minuto, pero indicando que NO hace nada
        logger.info(f"[HEARTBEAT] {symbol} | Vela minuto {current_hour}:{current_minute:02d} recibida | Precio: {data.close} | Estado: Esperando cierre de hora.")

async def main():
    logger.info("INICIANDO BOT DE TRADING")
    logger.info(f"Inversión por operación: ${USD_PER_TRADE}")
    logger.info(f"Guardando logs en CSV: {CSV_FILENAME}")
    logger.info("Conectando al stream de datos...")
    
    # Inicializar
    for s in SYMBOLS: last_processed_hour[s] = -1 
    
    stream_client.subscribe_bars(bar_handler, *SYMBOLS)
    
    logger.info("Escuchando mercado. Presiona Ctrl+C para detener.")
    await stream_client._run_forever()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot detenido por el usuario.")