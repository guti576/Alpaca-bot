import os
import time
import datetime
import pandas as pd

# Importaciones de Alpaca
from alpaca.trading.client import TradingClient
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit # <-- TimeFrameUnit añadido
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# Sustituye con tus credenciales de Paper Trading
API_KEY = "PK2CNGKUVBXK5XM75N64PIQIRL"
SECRET_KEY = "G1Ag2nzs6cFosZvBRp1QKTFLvw5nYBvNidn1W8Em9zNE"

trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)
data_client = CryptoHistoricalDataClient()

# --- NUEVA LISTA DE CRIPTOMONEDAS ---
SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD", "AVAX/USD"]
INVERSION_POR_OPERACION = 1000.00 # $10 a cada moneda

def get_signal(symbol):
    try:
        ahora_utc = datetime.datetime.now(datetime.timezone.utc)
        # Pedimos suficiente historial para calcular la media de 20 periodos sin problemas
        start_time = ahora_utc - datetime.timedelta(minutes=500)
        
        request_params = CryptoBarsRequest(
            symbol_or_symbols=[symbol],
            timeframe=TimeFrame(5, TimeFrameUnit.Minute),
            start=start_time,
            end=ahora_utc
        )
        
        bars = data_client.get_crypto_bars(request_params).df
        
        if bars.empty:
            print(f"[{symbol}] Esperando datos del mercado...")
            return "wait"
            
        df = bars.loc[symbol].copy()
        
        # --- NUEVO CÁLCULO DE DELAY (TIEMPO REAL) ---
        # Calculamos cuánto tiempo ha pasado desde que empezó a formarse la última vela
        delay_real_segundos = (ahora_utc - df.index[-1]).total_seconds()
        
        if delay_real_segundos < 300: # Si han pasado menos de 5 min (300s), estamos en la vela actual
            print(f"⚡ {symbol} -> Datos en tiempo real (Vela en formación).")
        else:
            retraso_red = delay_real_segundos - 300
            print(f"⏱️  {symbol} -> Delay de red: {int(retraso_red)} segundos.")
        
        # --- CÁLCULO DE BOLLINGER (20, 2) ---
        df['sma_20'] = df['close'].rolling(window=20).mean()
        df['std_dev'] = df['close'].rolling(window=20).std()
        df['upper_band'] = df['sma_20'] + (df['std_dev'] * 2)
        df['lower_band'] = df['sma_20'] - (df['std_dev'] * 2)
        
        current = df.iloc[-1]
        last_price = current['close']
        
        hora_actual = datetime.datetime.now().strftime('%H:%M:%S')
        print(f"[{hora_actual}] {symbol}: ${last_price:.2f} | B.Sup: ${current['upper_band']:.2f} | SMA20: ${current['sma_20']:.2f} | B.Inf: ${current['lower_band']:.2f}")
        
        # --- ESTRATEGIA (REVERSIÓN A LA MEDIA) ---
        if last_price <= current['lower_band']: return "buy"
        elif last_price >= current['upper_band']: return "sell"
        return "wait"
            
    except Exception as e:
        print(f"[{symbol}] Error calculando estrategia: {e}")
        return "wait"
    

def execute_trade(side, symbol):
    pos_symbol = symbol.replace("/", "") 
    
    positions = trading_client.get_all_positions()
    current_position = next((p for p in positions if p.symbol == pos_symbol), None)

    # 1. REVISIÓN DE STOP LOSS Y TAKE PROFIT SINTÉTICO
    if current_position:
        profit_pct = float(current_position.unrealized_plpc)
        print(f"📊 {symbol} -> ESTADO: Posición abierta | PnL actual: {profit_pct*100:.3f}%")
        
        if profit_pct >= 0.0075: # +0.75% Take Profit
            trading_client.close_position(pos_symbol) 
            print(f"✅ {symbol} -> TAKE PROFIT: Posición cerrada con ganancia del {profit_pct*100:.2f}%")
            return 
            
        elif profit_pct <= -0.005: # -0.50% Stop Loss
            trading_client.close_position(pos_symbol) 
            print(f"🛑 {symbol} -> STOP LOSS: Posición cerrada con pérdida del {profit_pct*100:.2f}%")
            return 
    else:
        print(f"👀 {symbol} -> ESTADO: Sin posiciones abiertas.")

    # 2. EJECUCIÓN DE SEÑALES
    if side == "buy":
        if not current_position:
            # VERIFICACIÓN DE SALDO (PROTECCIÓN DE $1000)
            account = trading_client.get_account()
            if float(account.buying_power) < INVERSION_POR_OPERACION:
                print(f"⚠️  {symbol} -> IGNORADO: Señal de COMPRA, pero no hay saldo suficiente (${account.buying_power}).")
                return
                
            order_data = MarketOrderRequest(
                symbol=symbol,
                notional=INVERSION_POR_OPERACION,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.GTC
            )
            trading_client.submit_order(order_data)
            print(f"🚀 {symbol} -> ACCIÓN: COMPRA de ${INVERSION_POR_OPERACION}. Precio cruzó Banda Inferior.")
        else:
            print(f"⏳ {symbol} -> IGNORADO: Señal de COMPRA, pero YA TIENES posición.")

    elif side == "sell":
        if current_position:
            trading_client.close_position(pos_symbol)
            print(f"🔄 {symbol} -> ACCIÓN: VENTA (Cierre). Precio cruzó Banda Superior.")
        else:
            print(f"⏳ {symbol} -> IGNORADO: Señal de VENTA, pero NO HAY posición.")
            
    elif side == "wait":
        if current_position:
            print(f"⏸️  {symbol} -> ACCIÓN: Manteniendo posición abierta (Buscando TP o B.Sup)...")
        else:
            print(f"⏸️  {symbol} -> ACCIÓN: Esperando oportunidad...")

print("--- Bot Iniciado en modo Paper Trading ---")
try:
        while True:
            # Limpia la celda para que no sature la memoria de tu navegador
            #clear_output(wait=True) 
            
            print("=" * 75)
            hora_ciclo = datetime.datetime.now().strftime('%H:%M:%S')
            print(f"🤖 Bot Scalper (Bollinger 5m | $1K) | Escaneo: [{hora_ciclo}]")
            print("=" * 75)
            
            for crypto in SYMBOLS:
                signal = get_signal(crypto)
                execute_trade(signal, crypto)
                print("-" * 55) 
                
            print(f"\n⏳ Escaneo finalizado. Próxima actualización de datos en 60 segundos...")
            time.sleep(60) 
            
except KeyboardInterrupt:
    print("\n🛑 Bot detenido manualmente por el usuario.")