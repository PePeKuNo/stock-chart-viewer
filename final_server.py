import sys
sys.stdout.flush()
print('Stock Chart Server starting...', flush=True)

import socket
import threading
import json
import urllib.request
from urllib.parse import urlparse, parse_qs
import os
import traceback

PORT = 3004
os.chdir(r'C:\Users\Bohdan\Desktop\taskk')

YAHOO_BASE = 'https://query1.finance.yahoo.com/v8/finance/chart/'

RANGE_MAP = {
    '1d':  {'range': '1d',  'interval': '5m'},
    '5d':  {'range': '5d',  'interval': '30m'},
    '1wk': {'range': '1wk', 'interval': '1h'},
    '1mo': {'range': '1mo', 'interval': '1d'},
    '3mo': {'range': '3mo', 'interval': '1d'},
    '1y':  {'range': '1y',  'interval': '1d'},
    '5y':  {'range': '5y',  'interval': '1wk'}
}

VALID_INTERVALS = {
    '1d':  ['1m','2m','5m','15m','30m','60m','90m'],
    '5d':  ['5m','15m','30m','60m','90m','1h'],
    '1wk': ['15m','30m','60m','90m','1h','1d'],
    '1mo': ['30m','60m','90m','1h','1d'],
    '3mo': ['1h','1d','1wk'],
    '1y':  ['1h','1d','1wk','1mo'],
    '5y':  ['1d','1wk','1mo']
}

def fetch_yahoo(symbol, timeframe, interval):
    print(f'fetch_yahoo: {symbol} {timeframe} {interval}', flush=True)
    config = RANGE_MAP.get(timeframe, RANGE_MAP['1wk'])
    yahoo_interval = interval or config['interval']
    if yahoo_interval not in VALID_INTERVALS.get(config['range'], []):
        yahoo_interval = config['interval']
    url = f"{YAHOO_BASE}{symbol}?range={config['range']}&interval={yahoo_interval}&includePrePost=false"
    print(f'Yahoo URL: {url}', flush=True)
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    if data.get('chart', {}).get('error'):
        raise Exception(data['chart']['error'].get('description', 'Symbol not found'))
    result = data['chart']['result'][0]
    if not result or not result.get('timestamp') or not result['indicators']['quote'][0]:
        raise Exception('No data available')
    ts_list = result['timestamp']
    quotes = result['indicators']['quote'][0]
    meta = result['meta']
    prices = []
    for i, ts in enumerate(ts_list):
        if all(k in quotes and quotes[k][i] is not None for k in ['open','high','low','close','volume']):
            prices.append({
                'timestamp': ts * 1000,
                'open': quotes['open'][i],
                'high': quotes['high'][i],
                'low': quotes['low'][i],
                'close': quotes['close'][i],
                'volume': quotes['volume'][i]
            })
    if not prices:
        raise Exception('No valid price data')
    return {
        'symbol': meta.get('symbol', symbol),
        'name': meta.get('longName') or meta.get('shortName') or symbol,
        'currency': meta.get('currency', 'USD'),
        'exchange': meta.get('exchangeName', ''),
        'timeframe': timeframe,
        'interval': yahoo_interval,
        'prices': prices
    }

def handle_request(conn):
    try:
        req = conn.recv(8192).decode('utf-8', errors='ignore')
        if not req: return
        lines = req.split('\r\n')
        if not lines: return
        parts = lines[0].split(' ', 2)
        if len(parts) < 3: return
        method, path, _ = parts
        print(f'Request: {method} {path}', flush=True)
        
        cors = 'Access-Control-Allow-Origin: *\r\nAccess-Control-Allow-Methods: GET, OPTIONS\r\nAccess-Control-Allow-Headers: Content-Type\r\n'
        
        if method == 'OPTIONS':
            conn.send(f'HTTP/1.1 200 OK\r\n{cors}\r\n'.encode())
            return
        
        parsed = urlparse(path)
        
        if parsed.path == '/' or parsed.path == '/index.html':
            with open('index.html', 'rb') as f:
                content = f.read()
            resp = (
                f'HTTP/1.1 200 OK\r\n'
                f'Content-Type: text/html; charset=utf-8\r\n'
                f'Content-Length: {len(content)}\r\n'
                f'{cors}\r\n'
            ).encode() + content
            conn.send(resp)
            
        elif parsed.path == '/api/stock':
            params = parse_qs(parsed.query)
            symbol = params.get('symbol', [''])[0].upper()
            timeframe = params.get('timeframe', ['1wk'])[0]
            interval = params.get('interval', [''])[0]
            
            if not symbol:
                body = json.dumps({'error': 'Symbol parameter is required'}).encode()
                conn.send(
                    f'HTTP/1.1 400 Bad Request\r\n'
                    f'Content-Type: application/json\r\n'
                    f'Content-Length: {len(body)}\r\n'
                    f'{cors}\r\n'.encode() + body
                )
                return
            
            try:
                data = fetch_yahoo(symbol, timeframe, interval)
                body = json.dumps(data).encode()
                conn.send(
                    f'HTTP/1.1 200 OK\r\n'
                    f'Content-Type: application/json\r\n'
                    f'Content-Length: {len(body)}\r\n'
                    f'{cors}\r\n'.encode() + body
                )
            except Exception as e:
                body = json.dumps({'error': str(e)}).encode()
                conn.send(
                    f'HTTP/1.1 500 Internal Server Error\r\n'
                    f'Content-Type: application/json\r\n'
                    f'Content-Length: {len(body)}\r\n'
                    f'{cors}\r\n'.encode() + body
                )
        else:
            # Serve static files
            filepath = parsed.path.lstrip('/')
            if not filepath:
                filepath = 'index.html'
            if os.path.exists(filepath):
                with open(filepath, 'rb') as f:
                    content = f.read()
                ext = os.path.splitext(filepath)[1].lower()
                mime = {
                    '.html': 'text/html; charset=utf-8',
                    '.js': 'application/javascript',
                    '.css': 'text/css',
                    '.json': 'application/json',
                    '.png': 'image/png',
                    '.jpg': 'image/jpeg',
                    '.ico': 'image/x-icon'
                }.get(ext, 'application/octet-stream')
                response = (
                    f'HTTP/1.1 200 OK\r\n'
                    f'Content-Type: {mime}\r\n'
                    f'Content-Length: {len(content)}\r\n'
                    f'{cors}\r\n'
                ).encode() + content
                conn.send(response)
            else:
                conn.send(b'HTTP/1.1 404 Not Found\r\n\r\n')
                
    except Exception as e:
        print(f'Error: {e}', flush=True)
        conn.send(b'HTTP/1.1 500 Internal Server Error\r\n\r\n')
    finally:
        conn.close()

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', PORT))
    server.listen(20)
    print(f'Server running on http://0.0.0.0:{PORT}', flush=True)
    print(f'Local: http://127.0.0.1:{PORT}', flush=True)
    print(f'Network: http://<your-ip>:{PORT}', flush=True)
    
    while True:
        conn, addr = server.accept()
        print(f'Connection from {addr}', flush=True)
        threading.Thread(target=handle_request, args=(conn,), daemon=True).start()

if __name__ == '__main__':
    main()