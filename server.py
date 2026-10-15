#!/usr/bin/env python3
"""
Simple HTTP server for stock chart viewer with Yahoo Finance API proxy.
"""
import http.server
import socketserver
import json
import urllib.request
import urllib.parse
import urllib.error
import mimetypes
import os
import sys
from pathlib import Path

PORT = int(os.environ.get('PORT', 3000))
DIRECTORY = Path(__file__).parent

# Yahoo Finance API base URL
YAHOO_FINANCE_BASE = 'https://query1.finance.yahoo.com/v8/finance/chart/'

# Map timeframe to Yahoo Finance parameters
YAHOO_PARAMS = {
    '1d': {'range': '1d', 'interval': '5m'},
    '5d': {'range': '5d', 'interval': '30m'},
    '1wk': {'range': '1wk', 'interval': '1h'},
    '1mo': {'range': '1mo', 'interval': '1d'},
    '3mo': {'range': '3mo', 'interval': '1d'},
    '1y': {'range': '1y', 'interval': '1d'},
    '5y': {'range': '5y', 'interval': '1wk'}
}

# Valid interval/range combinations for Yahoo Finance
# Based on Yahoo Finance API limitations
VALID_COMBINATIONS = {
    '1d': ['1m', '2m', '5m', '15m', '30m', '60m', '90m'],
    '5d': ['5m', '15m', '30m', '60m', '90m', '1h'],
    '1wk': ['15m', '30m', '60m', '90m', '1h', '1d'],
    '1mo': ['30m', '60m', '90m', '1h', '1d'],
    '3mo': ['1h', '1d', '1wk'],
    '1y': ['1h', '1d', '1wk', '1mo'],
    '5y': ['1d', '1wk', '1mo']
}

class StockChartHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIRECTORY), **kwargs)
    
    def end_headers(self):
        # Enable CORS
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()
    
    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        
        # API endpoint for stock data
        if parsed_url.path == '/api/stock':
            self.handle_stock_api(parsed_url)
            return
        
        # Serve static files
        super().do_GET()
    
    def handle_stock_api(self, parsed_url):
        query_params = urllib.parse.parse_qs(parsed_url.query)
        
        symbol = query_params.get('symbol', [''])[0].upper()
        timeframe = query_params.get('timeframe', ['1wk'])[0]
        interval = query_params.get('interval', [''])[0]
        
        if not symbol:
            self.send_json_response(400, {'error': 'Symbol parameter is required'})
            return
        
        try:
            data = self.fetch_yahoo_data(symbol, timeframe, interval)
            self.send_json_response(200, data)
        except Exception as e:
            self.send_json_response(500, {'error': str(e)})
    
    def fetch_yahoo_data(self, symbol, timeframe, interval):
        params = YAHOO_PARAMS.get(timeframe, YAHOO_PARAMS['1wk'])
        
        # Validate and auto-correct interval for the given timeframe
        valid_intervals = VALID_COMBINATIONS.get(params['range'], [])
        yahoo_interval = interval or params['interval']
        
        if yahoo_interval not in valid_intervals:
            # Auto-correct to the default interval for this timeframe
            yahoo_interval = params['interval']
        
        url = f"{YAHOO_FINANCE_BASE}{symbol}?range={params['range']}&interval={yahoo_interval}&includePrePost=false"
        
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        if data.get('chart', {}).get('error'):
            raise Exception(data['chart']['error'].get('description', 'Symbol not found'))
        
        result = data['chart']['result'][0]
        if not result or not result.get('timestamp') or not result['indicators']['quote'][0]:
            raise Exception('No data available for this symbol')
        
        timestamps = result['timestamp']
        quotes = result['indicators']['quote'][0]
        meta = result['meta']
        
        # Combine data points
        prices = []
        for i, ts in enumerate(timestamps):
            if all(k in quotes and quotes[k][i] is not None for k in ['open', 'high', 'low', 'close', 'volume']):
                prices.append({
                    'timestamp': ts * 1000,  # Convert to milliseconds
                    'open': quotes['open'][i],
                    'high': quotes['high'][i],
                    'low': quotes['low'][i],
                    'close': quotes['close'][i],
                    'volume': quotes['volume'][i]
                })
        
        if not prices:
            raise Exception('No valid price data available')
        
        return {
            'symbol': meta.get('symbol', symbol),
            'name': meta.get('longName') or meta.get('shortName') or symbol,
            'currency': meta.get('currency', 'USD'),
            'exchange': meta.get('exchangeName', ''),
            'timeframe': timeframe,
            'interval': yahoo_interval,
            'prices': prices
        }
    
    def send_json_response(self, status, data):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))
    
    def log_message(self, format, *args):
        # Suppress default log messages
        pass

def run_server():
    os.chdir(DIRECTORY)
    
    with socketserver.TCPServer(("0.0.0.0", PORT), StockChartHandler) as httpd:
        print(f"Server running on http://0.0.0.0:{PORT}")
        print(f"Accessible on your network at http://<your-ip>:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")
            httpd.shutdown()

if __name__ == '__main__':
    run_server()