from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------
# 1. FUNCIONES DE ESTRATEGIA
# ---------------------------------------------------------
def calculate_indicators(df):
    """
    Calcula SMA20, SMA50 y RSI usando únicamente Pandas puro.
    """
    if df is None or df.empty:
        return None
        
    df_calc = df.copy()
    close = df_calc['close']
    
    # 1. Medias Móviles Simples (Muy fácil con rolling)
    df_calc['SMA20'] = close.rolling(window=20).mean()
    df_calc['SMA50'] = close.rolling(window=50).mean()
    
    # 2. Cálculo del RSI (Wilder's Smoothing)
    delta = close.diff()
    
    # Separar ganancias y pérdidas
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    
    # Medias Móviles Exponenciales (Alpha = 1/14 para el método Wilder clásico)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    
    # Relative Strength (RS) y RSI final
    rs = avg_gain / avg_loss
    df_calc['RSI'] = 100 - (100 / (1 + rs))
    
    # Limpiamos los NaN generados por los periodos de cálculo iniciales
    df_calc.dropna(inplace=True)
    
    return df_calc


def run_strategy_analysis(df, symbol, TAKE_PROFIT_PCT=1.04, STOP_LOSS_PCT=0.98):
    """
    Analiza el DataFrame y devuelve un diccionario con la decisión y los datos para el log.
    """
    # Si no hay datos suficientes, devolvemos un log de error/espera
    if df is None or len(df) < 50:
        return {
            'utc_time': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
            'symbol': symbol,
            'action': 'ERROR_INSUFFICIENT_DATA',
            'price': 0.0,
            'details': 'Faltan datos para calcular medias móviles'
        }
        
    close = df['close']
    sma20 = df['SMA20']
    sma50 = df['SMA50']
    rsi = df['RSI']
    
    current_price = round(float(close.iloc[-1]), 2)
    prev_close = float(close.iloc[-2])
    last_sma20 = float(sma20.iloc[-1])
    prev_sma20 = float(sma20.iloc[-2])
    
    # --- EVALUACIÓN DE REGLAS ---
    was_down = (close < sma50).tail(15).all()
    touched_bottom = rsi.tail(10).min() < 35
    crossed_up = (current_price > last_sma20) and (prev_close <= prev_sma20)
    overbought = float(rsi.iloc[-1]) > 70

    # Calculamos niveles para el log
    tp_price = round(current_price * TAKE_PROFIT_PCT, 2)
    sl_price = round(current_price * STOP_LOSS_PCT, 2)
    
    utc_now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

    # --- TOMA DE DECISIÓN ---
    if was_down and touched_bottom and crossed_up:
        return {
            'utc_time': utc_now,
            'symbol': symbol,
            'action': 'ENTRY_BRACKET_BUY',
            'price': current_price,
            'details': f'TP:{tp_price}/SL:{sl_price}'
        }, 1
        
    elif overbought:
        return {
            'utc_time': utc_now,
            'symbol': symbol,
            'action': 'SELL_SIGNAL',
            'price': current_price,
            'details': 'Sobrecompra (RSI > 70)'
        }, -1
        
    else:
        return {
            'utc_time': utc_now,
            'symbol': symbol,
            'action': 'HOLD',
            'price': current_price,
            'details': 'Esperando confirmación'
        }, 0