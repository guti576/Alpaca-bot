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

from my_functions import *
from buy_the_dip.buy_the_dip import *

# --- CONFIGURACIÓN ---
API_KEY = "PKILMNVKETV5POH5GOPM37W37E"
SECRET_KEY = "DcQGFZBAdWpLc7iuBUVdAn8PdAYrnpPF93CCaRaXsjcG"
CSV_FILENAME = 'buy_the_dip_trading_journal_stocks.csv'

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
USD_PER_TRADE = 10.0 

# Configuración de Riesgo
TAKE_PROFIT_PCT = 1.04  # +4%
STOP_LOSS_PCT = 0.98    # -2%

# Clientes de Alpaca para Stocks
trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)
data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
stream_client = StockDataStream(API_KEY, SECRET_KEY)

# Control de hora
last_processed_hour = {}

# ---------------------------------------------------------
# GESTOR DE EVENTOS (Orquestador vía WebSocket)
# ---------------------------------------------------------
async def bar_handler(data):
    symbol = data.symbol
    current_hour = data.timestamp.hour

    # BUSCAMOS ENTRADAS SOLO AL CAMBIAR DE HORA
    if symbol not in last_processed_hour or last_processed_hour[symbol] != current_hour:
        last_processed_hour[symbol] = current_hour
        
        # Pausa para evitar exceder el rate-limit de la API al consultar acciones de golpe
        await asyncio.sleep(3) 
        #try:
        df = get_historical_data(data_client, symbol, TIMEFRAME_STRATEGY)
        df = calculate_indicators(df)
        logs, signal = run_strategy_analysis(df, symbol, TAKE_PROFIT_PCT, STOP_LOSS_PCT)
        if signal == 1:
            log_to_csv(logs, CSV_FILENAME)
        #except Exception as e:
        #    print(f"Error estrategia {symbol}: {e}")

async def main():
    print(f"🤖 Bot Stocks Iniciado.")
    print(f"   Estrategia: Entradas en velas 1H (buy the dip)")
    print(f"   Gestión: BRACKET ORDERS automáticas (SL -2% / TP +4%)")
    print(f"   Monitorizando {len(SYMBOLS)} acciones del S&P 500...")
    
    for s in SYMBOLS: last_processed_hour[s] = -1 
    
    # Nos suscribimos al stream de barras de las acciones
    stream_client.subscribe_bars(bar_handler, *SYMBOLS)
    await stream_client._run_forever()

if __name__ == "__main__":
    asyncio.run(main())