import os
import datetime

# Importamos el cliente de Streaming en Vivo (WebSockets)
from alpaca.data.live.crypto import CryptoDataStream

# 1. CARGAR CONFIGURACIÓN
API_KEY = "PK2CNGKUVBXK5XM75N64PIQIRL"
SECRET_KEY = "G1Ag2nzs6cFosZvBRp1QKTFLvw5nYBvNidn1W8Em9zNE"

# 2. INICIAR EL CLIENTE DE STREAMING
# Usamos el stream de Criptomonedas de Alpaca
stream = CryptoDataStream(API_KEY, SECRET_KEY)

# 3. CREAR LA FUNCIÓN RECEPTORA (El "Escuchador")
# Esta función es asíncrona (async) porque se quedará dormida hasta que llegue el dato
# Creamos un diccionario global para guardar la vela en formación de cada moneda
velas_15m = {}

async def manejador_de_velas(bar):
    ahora_utc = datetime.datetime.now(datetime.timezone.utc)
    vela_ts = bar.timestamp 
    moneda = bar.symbol
    
    # --- 1. LÓGICA DEL ACUMULADOR OHLC ---
    # Si la moneda no está en el diccionario, O si estamos en el minuto exacto donde empieza un nuevo bloque (:00, :15, :30, :45)
    if (moneda not in velas_15m) or (vela_ts.minute % 15 == 0):
        # Iniciamos una vela de 15m completamente nueva
        velas_15m[moneda] = {
            'open': bar.open,
            'high': bar.high,
            'low': bar.low,
            'close': bar.close,
            'volume': bar.volume,
            'trade_count': bar.trade_count
        }
    else:
        # Si estamos en el medio del bloque, actualizamos la vela existente
        # El Open se queda igual (es el del inicio).
        # El High es el valor máximo entre el High que teníamos y el High de esta vela de 1m
        velas_15m[moneda]['high'] = max(velas_15m[moneda]['high'], bar.high)
        # El Low es el valor mínimo entre el Low que teníamos y el Low de esta vela de 1m
        velas_15m[moneda]['low'] = min(velas_15m[moneda]['low'], bar.low)
        # El Close siempre se actualiza con el de la última vela recibida
        velas_15m[moneda]['close'] = bar.close
        # Acumulamos el volumen y los trades
        velas_15m[moneda]['volume'] += bar.volume
        velas_15m[moneda]['trade_count'] += bar.trade_count

    # --- 2. CÁLCULO DEL DELAY ---
    segundos_desde_inicio = (ahora_utc - vela_ts).total_seconds()
    delay_ms = (segundos_desde_inicio - 60) * 1000 
    hora_pantalla = ahora_utc.strftime('%H:%M:%S.%f')[:-3]
    
    # --- 3. EVALUACIÓN Y CIERRE DEL BLOQUE DE 15 MINUTOS ---
    # Si estamos en la última vela del bloque (:14, :29, :44 o :59)
    if (vela_ts.minute + 1) % 15 == 0:
        vela_final = velas_15m[moneda] # Extraemos nuestra vela OHLC terminada
        
        print("=" * 75)
        print(f"[{hora_pantalla}] 🚨 ¡VELA DE 15 MINUTOS CERRADA! {moneda}")
        print(f"   📊 OHLC -> Open: ${vela_final['open']:.2f} | High: ${vela_final['high']:.2f} | Low: ${vela_final['low']:.2f} | Close: ${vela_final['close']:.2f}")
        print(f"   ⏱️ Delay red: {delay_ms:.0f} ms | 🔥 Trades Totales: {vela_final['trade_count']}")
        print("   🧠 -> Iniciando cálculo de Bandas de Bollinger y Evaluación de Estrategia...")
        print("=" * 75)
        
        # ---> AQUÍ PASARÍAS EL PRECIO DE CIERRE FINAL (vela_final['close']) A TU ESTRATEGIA <---
        
    else:
        # Durante los 14 minutos de formación de la vela...
        minutos_restantes = 15 - ((vela_ts.minute + 1) % 15)
        precio_actual = velas_15m[moneda]['close']
        
        # Opcional: Imprimir cómo se va formando la vela
        print(f"[{hora_pantalla}] ⏱️ {moneda} | Precio Actual: ${precio_actual:.2f} | Faltan {minutos_restantes} min para cerrar la vela de 15'.")
        
        # ---> AQUÍ ES DONDE DEBES PONER LA REVISIÓN DE TU STOP LOSS SINTÉTICO <---
        # Porque si el precio se desploma en el minuto 7, no quieres esperar al minuto 15 para vender.

# 4. SUSCRIBIRSE A LAS MONEDAS
# Le decimos a Alpaca: "Avisáme CADA VEZ que se cierre una vela de 1 minuto para estas monedas"
monedas_a_vigilar = ["BTC/USD", "ETH/USD"]
stream.subscribe_bars(manejador_de_velas, *monedas_a_vigilar)

# 5. MANTENER LA CONEXIÓN ABIERTA
if __name__ == "__main__":
    print("==================================================")
    print("📡 CONECTANDO AL WEBSOCKET DE ALPACA...")
    print(f"   Vigilando velas de 1 minuto para: {', '.join(monedas_a_vigilar)}")
    print("==================================================")
    
    try:
        # Esto inicia el bucle infinito. No necesitas time.sleep()
        stream.run() 
    except KeyboardInterrupt:
        print("\n🛑 Desconectado del WebSocket.")