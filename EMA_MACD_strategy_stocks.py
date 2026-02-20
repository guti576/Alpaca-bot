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

# --- CONFIGURACIÓN ---
API_KEY = "PK2CNGKUVBXK5XM75N64PIQIRL"
SECRET_KEY = "G1Ag2nzs6cFosZvBRp1QKTFLvw5nYBvNidn1W8Em9zNE"
CSV_FILENAME = 'trading_journal_stocks.csv'

SYMBOLS = [
    # --- Mega-Cap & Big Tech ---
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'META', 'GOOGL', 'GOOG', 'TSLA',
    
    # --- Semiconductores & Hardware ---
    'AMD', 'INTC', 'AVGO', 'QCOM', 'TXN', 'MU', 'AMAT', 'LRCX', 'KLAC', 'ARM', 'SMCI',
    
    # --- Software, Cloud & Ciberseguridad ---
    'CRM', 'ADBE', 'NOW', 'SNOW', 'PLTR', 'CRWD', 'PANW', 'FTNT', 'DDOG', 'NET', 
    'ZS', 'WDAY', 'INTU', 'ORCL', 'IBM', 'MSTR', 'TEAM', 'FSLY', 'OKTA', 'DOCU',
    
    # --- Finanzas & Pagos ---
    'JPM', 'BAC', 'WFC', 'C', 'GS', 'MS', 'V', 'MA', 'AXP', 'PYPL', 'SQ', 
    'HOOD', 'COIN', 'SOFI', 'BLK', 'SCHW', 'SPGI', 'CME', 'PGR', 'CB',
    
    # --- Salud & Farmacéuticas ---
    'LLY', 'UNH', 'JNJ', 'MRK', 'ABBV', 'TMO', 'ABT', 'DHR', 'PFE', 'AMGN', 
    'ISRG', 'GILD', 'BIIB', 'VRTX', 'REGN', 'BMY', 'CVS', 'CI', 'HUM',
    
    # --- Consumo Discrecional & Retail ---
    'WMT', 'TGT', 'COST', 'HD', 'LOW', 'MCD', 'SBUX', 'NKE', 'LULU', 'CMG', 
    'ROST', 'TJX', 'DG', 'DLTR', 'EBAY', 'ETSY', 'CHWY',
    
    # --- Consumo Defensivo ---
    'PG', 'PEP', 'KO', 'PM', 'MO', 'MDLZ', 'K', 'GIS', 'CL', 'KMB', 'HSY',
    
    # --- Comunicaciones, Media & Entretenimiento ---
    'NFLX', 'DIS', 'CMCSA', 'T', 'VZ', 'TMUS', 'WBD', 'PARA', 'SPOT', 'ROKU', 
    'TTWO', 'EA', 'LYV', 'PINS', 'SNAP', 'RDDT',
    
    # --- Automoción, Viajes & Transporte ---
    'F', 'GM', 'UBER', 'LYFT', 'ABNB', 'BKNG', 'EXPE', 'RCL', 'CCL', 'NCLH', 
    'DAL', 'UAL', 'AAL', 'LUV', 'UPS', 'FDX', 'CSX', 'UNP', 'NSC',
    
    # --- Industriales, Aeroespacial & Defensa ---
    'BA', 'LMT', 'RTX', 'GD', 'NOC', 'CAT', 'DE', 'GE', 'MMM', 'HON', 
    'WM', 'RSG', 'EMR', 'ETN', 'PH',
    
    # --- Energía & Materiales ---
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'PXD', 'MPC', 'VLO', 'OXY', 'HAL', 
    'FCX', 'NUE', 'ALB', 'LIN', 'APD',
    
    # --- Real Estate (REITs) ---
    'PLD', 'AMT', 'EQIX', 'CCI', 'PSA', 'O', 'SPG', 'WELL', 'DLR',
    
    # --- Alta Volatilidad / Meme / Otros ---
    'GME', 'AMC', 'PLUG', 'ENPH', 'FSLR', 'RBLX', 'DKNG', 'PTON', 'LCID', 'RIVN', 'NIO'
]

TIMEFRAME_STRATEGY = TimeFrame.Hour
USD_PER_TRADE = 500.0 

# Configuración de Riesgo
TAKE_PROFIT_PCT = 1.04  # +4%
STOP_LOSS_PCT = 0.98    # -2%

# Clientes de Alpaca para Stocks
trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)
data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
stream_client = StockDataStream(API_KEY, SECRET_KEY)

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
# 1. FUNCIONES DE ESTRATEGIA (EMA/MACD) - Se ejecuta CADA HORA
# ---------------------------------------------------------
def get_historical_data(symbol):
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

def calculate_indicators(df):
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    k = df['close'].ewm(span=12, adjust=False).mean()
    d = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = k - d
    df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    return df

def run_strategy_analysis(symbol):
    current_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    print(f"{current_time} - 🔎 Analizando estrategia 1H para {symbol}...")
    
    # 1. Comprobar si ya tenemos posición
    try:
        trading_client.get_open_position(symbol)
        print(f"   Posición existente en {symbol}. Saltando análisis.")
        return
    except:
        pass # No hay posición, procedemos

    # 2. Descargar y calcular
    df = get_historical_data(symbol)
    df = calculate_indicators(df)
    
    df_closed = df[df['is_closed'] == True]
    if len(df_closed) < 200: 
        print(f"   Datos insuficientes para {symbol} (Requiere 200 velas).")
        return

    curr = df_closed.iloc[-1]
    prev = df_closed.iloc[-2]
    
    # 3. Señales
    is_uptrend = curr['close'] > curr['ema200']
    macd_crossover = (prev['macd'] < prev['signal']) and (curr['macd'] > curr['signal'])
    is_pullback = curr['macd'] < 0
    
    if is_uptrend and macd_crossover:# and is_pullback:
        current_price = curr['close']
        
        # Cantidad en números enteros para acciones por seguridad con brackets
        qty = int(USD_PER_TRADE // current_price) 
        if qty <= 0:
            print(f"   Fondos insuficientes o precio muy alto para comprar 1 acción de {symbol}.")
            return

        # Calcular niveles de SL y TP
        tp_price = round(current_price * TAKE_PROFIT_PCT, 2)
        sl_price = round(current_price * STOP_LOSS_PCT, 2)
        
        print(f"✅ SEÑAL DE COMPRA: {symbol} a {current_price:.2f}")
        print(f"   Configurando Bracket: TP @ {tp_price} | SL @ {sl_price}")
        
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
        trading_client.submit_order(req)
        
        log_to_csv({
            'utc_time': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
            'symbol': symbol,
            'action': 'ENTRY_BRACKET_BUY',
            'price': current_price,
            'details': f'TP:{tp_price}/SL:{sl_price}'
        })
    else:
        print(f"   Condiciones no cumplidas en {symbol} (Tendencia alcista:{is_uptrend} | Cruce MACD:{macd_crossover} | Pullback:{is_pullback})")

# ---------------------------------------------------------
# 2. GESTOR DE EVENTOS (Orquestador vía WebSocket)
# ---------------------------------------------------------
async def bar_handler(data):
    symbol = data.symbol
    current_hour = data.timestamp.hour

    # BUSCAMOS ENTRADAS SOLO AL CAMBIAR DE HORA
    if symbol not in last_processed_hour or last_processed_hour[symbol] != current_hour:
        last_processed_hour[symbol] = current_hour
        
        # Pausa para evitar exceder el rate-limit de la API al consultar acciones de golpe
        await asyncio.sleep(3) 
        try:
            run_strategy_analysis(symbol)
        except Exception as e:
            print(f"Error estrategia {symbol}: {e}")

async def main():
    print(f"🤖 Bot de Acciones Iniciado.")
    print(f"   Estrategia: Entradas en velas 1H (EMA/MACD)")
    print(f"   Gestión: BRACKET ORDERS automáticas (SL -2% / TP +4%)")
    print(f"   Monitorizando {len(SYMBOLS)} acciones del S&P 500...")
    
    for s in SYMBOLS: last_processed_hour[s] = -1 
    
    # Nos suscribimos al stream de barras de las acciones
    stream_client.subscribe_bars(bar_handler, *SYMBOLS)
    await stream_client._run_forever()

if __name__ == "__main__":
    asyncio.run(main())