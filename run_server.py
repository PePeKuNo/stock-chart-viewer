import socketserver
import http.server
import os
import json
import urllib.request
from urllib.parse import urlparse, parse_qs

os.chdir(r'C:\Users\Bohdan\Desktop\taskk')
PORT = 3002

YAHOO_BASE = 'https://query1.finance.yahoo.com/v8/finance/chart/'
RANGE_MAP = {
    '1d': {'range': '1d', 'interval': '5m'},
    '5d': {'range': '5d', 'interval': '30m'},
    '1wk': {'range': '1wk', 'interval': '1h'},
    '1mo': {'range': '1mo', 'interval': '1d'},
    '3mo': {'range': '3mo', 'interval': '1d'},
    '1y': {'range': '1y', 'interval': '1d'},
    '5y': {'range': '5y', 'interval': '1wk'}
}
VALID_INTERVALS = {
    '1d': ['1m', '2m', '5m', '15m', '30m', '60m', '90m'],
    '5d': ['5m', '15m', '30m', '60m', '90m', '1h'],
    '1wk': ['15m', '30m', '60m', '90m', '1h', '1d'],
    '1mo': ['30m', '60m', '90m', '1h', '1d'],
    '3mo': ['1h', '1d', '1wk'],
    '1y': ['1h', '1d', '1wk', '1mo'],
    '5y': ['1d', '1wk', '1mo']
}

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        print(f'Request: {self.path}')
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            with open('index.html', 'rb') as f:
                self.wfile.write(f.read())
        elif self.path.startswith('/api/stock'):
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            symbol = params.get('symbol', [''])[0].upper()
            timeframe = params.get('timeframe', ['1wk'])[0]
            interval = params.get('interval', [''])[0]
            
            if not symbol:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"error": "Symbol parameter is required"}')
                return
            
            config = RANGE_MAP.get(timeframe, RANGE_MAP['1wk'])
            yahoo_interval = interval or config['interval']
            if yahoo_interval not in VALID_INTERVALS.get(config['range'], []):
                yahoo_interval = config['interval']
            
            url = f'{YAHOO_BASE}{symbol}?range={config["range"]}&interval={yahoo_interval}&includePrePost=false'
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            
            try:
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = json.loads(response.read().decode('utf-8'))
                
                if data.get('chart', {}).get('error'):
                    self.send_response(404)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(b'{"error": "Symbol not found"}')
                    return
                
                result = data['chart']['result'][0]
                if not result or not result.get('timestamp') or not result['indicators']['quote'][0]:
                    self.send_response(404)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(b'{"error": "No data available"}')
                    return
                
                timestamps = result['timestamp']
                quotes = result['indicators']['quote'][0]
                meta = result['meta']
                
                prices = []
                for i, ts in enumerate(timestamps):
                    if all(k in quotes and quotes[k][i] is not None for k in ['open', 'high', 'low', 'close', 'volume']):
                        prices.append({
                            'timestamp': ts * 1000,
                            'open': quotes['open'][i],
                            'high': quotes['high'][i],
                            'low': quotes['low'][i],
                            'close': quotes['close'][i],
                            'volume': quotes['volume'][i]
                        })
                
                if not prices:
                    self.send_response(404)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(b'{"error": "No valid price data"}')
                    return
                
                response_data = {
                    'symbol': meta.get('symbol', symbol),
                    'name': meta.get('longName') or meta.get('shortName') or symbol,
                    'currency': meta.get('currency', 'USD'),
                    'exchange': meta.get('exchangeName', ''),
                    'timeframe': timeframe,
                    'interval': yahoo_interval,
                    'prices': prices
                }
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(response_data).encode('utf-8'))
                
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(f'{{"error": "{str(e)}"}}'.encode('utf-8'))
        else:
            super().do_GET()
    
    def log_message(self, *args):
        pass

with socketserver.TCPServer(('', PORT), Handler) as httpd:
    print(f'Serving on port {PORT}')
    httpd.serve_forever()