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
async def manejador_de_velas(bar):
    # 1. CÁLCULO ULTRA-PRECISO DEL DELAY EN MILISEGUNDOS
    ahora_utc = datetime.datetime.now(datetime.timezone.utc)
    vela_ts = bar.timestamp
    
    # Calculamos los segundos totales desde que la vela INICIÓ
    segundos_desde_inicio = (ahora_utc - vela_ts).total_seconds()
    
    # Como es una vela de 1 minuto, restamos 60 segundos. 
    # Lo que sobra es el tiempo de viaje por internet (Delay de red). Lo multiplicamos por 1000 para ms.
    delay_ms = (segundos_desde_inicio - 60) * 1000 
    
    # 2. EXTRACCIÓN DE DATOS DE LA VELA
    moneda = bar.symbol
    cierre = bar.close
    
    # Parche para el bug de Alpaca:
    volumen_monedas = bar.volume
    num_operaciones = bar.trade_count # ¡Esta es la métrica fiable!
    
    # Formateamos la hora para que muestre los milisegundos en pantalla (.%f[:-3])
    hora_pantalla = ahora_utc.strftime('%H:%M:%S.%f')[:-3]
    
    # 3. IMPRESIÓN DEL PANEL
    print(f"[{hora_pantalla}] 🚨 VELA CERRADA: {moneda}")
    print(f"   Precio: ${cierre:.2f} | ⏱️ Delay de red: {delay_ms:.0f} ms")
    
    # Si el volumen viene a 0, mostramos una alerta y usamos los trades
    if volumen_monedas == 0:
        print(f"   Volumen: [Bug Alpaca=0] | 🔥 Operaciones (Trades) reales: {num_operaciones}")
    else:
        print(f"   Volumen: {volumen_monedas} | 🔥 Operaciones (Trades): {num_operaciones}")
        
    print("-" * 60)

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