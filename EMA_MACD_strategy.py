import asyncio
import pandas as pd
import os
import csv
from datetime import datetime, timezone, timedelta
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.live import CryptoDataStream
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# --- CONFIGURACIÓN ---
API_KEY = "PK2CNGKUVBXK5XM75N64PIQIRL"
SECRET_KEY = "G1Ag2nzs6cFosZvBRp1QKTFLvw5nYBvNidn1W8Em9zNE"
BASE_URL = 'https://paper-api.alpaca.markets'
CSV_FILENAME = 'trading_journal_monitor.csv'

SYMBOLS = [
    'BTC/USD', 'ETH/USD', 'SOL/USD', 
    'AVAX/USD', 'LINK/USD', 'LTC/USD', 'MATIC/USD'
]

TIMEFRAME_STRATEGY = TimeFrame.Hour
USD_PER_TRADE = 1000.0 

# Configuración de Riesgo
TAKE_PROFIT_PCT = 1.04  # +4%
STOP_LOSS_PCT = 0.98    # -2%

# Clientes
trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)
data_client = CryptoHistoricalDataClient()
stream_client = CryptoDataStream(API_KEY, SECRET_KEY)

# Control de hora
last_processed_hour = {}

def log_to_csv(data_dict):
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
# 1. FUNCIÓN DE MONITORIZACIÓN (SL y TP) - Se ejecuta CADA MINUTO
# ---------------------------------------------------------
def monitor_position(symbol, current_price):
    """
    Revisa si tenemos posición y si el precio actual toca el SL o el TP.
    """
    try:
        # Buscamos si tenemos posición en este símbolo
        position = None
        try:
            position = trading_client.get_open_position(symbol.replace('/', ''))
        except:
            return # No hay posición, no hay nada que monitorizar

        # Extraemos datos
        qty = float(position.qty)
        entry_price = float(position.avg_entry_price)
        
        # Calculamos límites
        tp_price = entry_price * TAKE_PROFIT_PCT
        sl_price = entry_price * STOP_LOSS_PCT
        
        reason = None
        
        # --- LÓGICA DE SALIDA ---
        if current_price >= tp_price:
            reason = f"TAKE_PROFIT (+4%) | Ent: {entry_price:.2f} -> Act: {current_price:.2f}"
        elif current_price <= sl_price:
            reason = f"STOP_LOSS (-2%) | Ent: {entry_price:.2f} -> Act: {current_price:.2f}"
        else:
            current_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            print(f"{current_time} - No SL ni TP alcanzado en {symbol}...")
            
        # Si hay razón para salir, vendemos
        if reason:
            print(f"\n🚨 CERRANDO POSICIÓN EN {symbol}: {reason}")
            req = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.GTC
            )
            trading_client.submit_order(req)
            
            log_to_csv({
                'utc_time': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
                'symbol': symbol,
                'action': 'EXIT',
                'price': current_price,
                'details': reason
            })

    except Exception as e:
        print(f"Error monitorizando {symbol}: {e}")

# ---------------------------------------------------------
# 2. FUNCIONES DE ESTRATEGIA (EMA/MACD) - Se ejecuta CADA HORA
# ---------------------------------------------------------
def get_historical_data(symbol):
    # Pedimos 20 días para asegurar cálculo correcto
    start_time = datetime.now(timezone.utc) - timedelta(days=20)
    req = CryptoBarsRequest(symbol_or_symbols=[symbol], timeframe=TIMEFRAME_STRATEGY, start=start_time, limit=1000)
    bars = data_client.get_crypto_bars(req)
    df = bars.df
    if isinstance(df.index, pd.MultiIndex): df = df.reset_index(level=0, drop=True)
    
    # Flag de cierre
    now_utc = datetime.now(timezone.utc)
    candle_starts = df.index.to_pydatetime()
    df['is_closed'] = [now_utc >= (t + timedelta(hours=1, seconds=1)) for t in candle_starts]
    return df

def calculate_indicators(df):
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    k = df['close'].ewm(span=12, adjust=False).mean()
    d = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = k - d
    df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    return df

def run_strategy_analysis(symbol):
    """Busca entradas solo si la vela de 1H acaba de cerrar"""
    current_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    print(f"{current_time} - 🔎 Analizando estrategia 1H para {symbol}...")
    
    # 1. Comprobar si ya tenemos posición (para no comprar doble)
    try:
        trading_client.get_open_position(symbol.replace('/', ''))
        print(f"   Posición existente en {symbol}. Saltando análisis de entrada.")
        return
    except:
        pass # No hay posición, procedemos

    # 2. Descargar y calcular
    df = get_historical_data(symbol)
    df = calculate_indicators(df)
    
    df_closed = df[df['is_closed'] == True]
    if len(df_closed) < 200: return

    curr = df_closed.iloc[-1]
    prev = df_closed.iloc[-2]
    
    # 3. Señales
    is_uptrend = curr['close'] > curr['ema200']
    macd_crossover = (prev['macd'] < prev['signal']) and (curr['macd'] > curr['signal'])
    is_pullback = curr['macd'] < 0
    
    if is_uptrend and macd_crossover and is_pullback:
        current_price = curr['close']
        
        # Calcular Cantidad
        raw_qty = USD_PER_TRADE / current_price
        
        if current_price >= 1:
            qty = round(raw_qty, 2)
        else:
            qty = round(raw_qty, 0) # Alpaca suele pedir enteros para monedas < $1
        
        print(f"✅ SEÑAL DE COMPRA: {symbol} a {current_price}")
        
        # Comprar (Sin Stop Loss ni Take Profit adjunto)
        req = MarketOrderRequest(symbol=symbol, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.GTC)
        trading_client.submit_order(req)
        
        log_to_csv({
            'utc_time': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
            'symbol': symbol,
            'action': 'ENTRY_BUY',
            'price': current_price,
            'details': 'EMA+MACD Signal'
        })
    else:
        print(f"Uptrend:{is_uptrend} | MACD crossover {macd_crossover} | Pullback {is_pullback} - No se cumplen los requisitos de entrada...")

# ---------------------------------------------------------
# 3. GESTOR DE EVENTOS (Orquestador)
# ---------------------------------------------------------
async def bar_handler(data):
    symbol = data.symbol
    current_price = data.close  # Precio de la barra de 1 minuto
    current_hour = data.timestamp.hour

    # A) TAREA CRÍTICA: Monitorizar Riesgo (SE EJECUTA SIEMPRE, CADA MINUTO)
    #    Esto asegura que si el precio cae a mitad de la hora, vendemos.
    monitor_position(symbol, current_price)

    # B) TAREA ESTRATÉGICA: Buscar Entradas (SOLO AL CAMBIAR DE HORA)
    if symbol not in last_processed_hour or last_processed_hour[symbol] != current_hour:
        last_processed_hour[symbol] = current_hour
        
        # Pequeña pausa para asegurar que Alpaca procesó el cierre de la vela de 1H
        await asyncio.sleep(2) 
        try:
            run_strategy_analysis(symbol)
        except Exception as e:
            print(f"Error estrategia {symbol}: {e}")

async def main():
    print(f"🤖 Bot Iniciado.")
    print(f"   Estrategia: Entradas en velas 1H (EMA/MACD)")
    print(f"   Gestión: Monitorización continua (SL -2% / TP +4%)")
    
    for s in SYMBOLS: last_processed_hour[s] = -1 
    
    # Nos suscribimos al stream. Alpaca envía barras de 1 minuto por defecto.
    stream_client.subscribe_bars(bar_handler, *SYMBOLS)
    await stream_client._run_forever()

if __name__ == "__main__":
    asyncio.run(main())