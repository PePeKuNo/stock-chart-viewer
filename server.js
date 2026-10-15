const http = require('http');
const fs = require('fs');
const path = require('path');
const https = require('https');

const PORT = process.env.PORT || 3000;

// MIME types
const mimeTypes = {
    '.html': 'text/html',
    '.js': 'application/javascript',
    '.css': 'text/css',
    '.json': 'application/json',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.gif': 'image/gif',
    '.svg': 'image/svg+xml',
    '.ico': 'image/x-icon'
};

// Yahoo Finance API base URL
const YAHOO_FINANCE_BASE = 'https://query1.finance.yahoo.com/v8/finance/chart/';

// Map timeframe to Yahoo Finance parameters
function getYahooParams(timeframe, interval) {
    const params = {
        '1d': { range: '1d', interval: '5m' },
        '5d': { range: '5d', interval: '30m' },
        '1wk': { range: '1wk', interval: '1h' },
        '1mo': { range: '1mo', interval: '1d' },
        '3mo': { range: '3mo', interval: '1d' },
        '1y': { range: '1y', interval: '1d' },
        '5y': { range: '5y', interval: '1wk' }
    };
    
    // Use user-specified interval if it makes sense for the timeframe
    const base = params[timeframe] || params['1wk'];
    return {
        range: base.range,
        interval: interval || base.interval
    };
}

// Fetch data from Yahoo Finance
function fetchFromYahoo(symbol, timeframe, interval) {
    return new Promise((resolve, reject) => {
        const { range, interval: yahooInterval } = getYahooParams(timeframe, interval);
        const url = `${YAHOO_FINANCE_BASE}${symbol}?range=${range}&interval=${yahooInterval}&includePrePost=false`;
        
        https.get(url, (res) => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                try {
                    const json = JSON.parse(data);
                    
                    if (json.chart.error) {
                        reject(new Error(json.chart.error.description || 'Symbol not found'));
                        return;
                    }
                    
                    const result = json.chart.result[0];
                    if (!result || !result.timestamp || !result.indicators.quote[0]) {
                        reject(new Error('No data available for this symbol'));
                        return;
                    }
                    
                    const timestamps = result.timestamp;
                    const quotes = result.indicators.quote[0];
                    const meta = result.meta;
                    
                    // Combine data points
                    const prices = timestamps.map((ts, i) => ({
                        timestamp: ts * 1000, // Convert to milliseconds
                        open: quotes.open[i],
                        high: quotes.high[i],
                        low: quotes.low[i],
                        close: quotes.close[i],
                        volume: quotes.volume[i]
                    })).filter(p => p.close !== null && p.open !== null && p.high !== null && p.low !== null);
                    
                    if (prices.length === 0) {
                        reject(new Error('No valid price data available'));
                        return;
                    }
                    
                    resolve({
                        symbol: meta.symbol,
                        name: meta.longName || meta.shortName || symbol,
                        currency: meta.currency,
                        exchange: meta.exchangeName,
                        timeframe: timeframe,
                        interval: yahooInterval,
                        prices: prices
                    });
                } catch (e) {
                    reject(new Error('Failed to parse Yahoo Finance data'));
                }
            });
        }).on('error', (err) => {
            reject(new Error('Network error: ' + err.message));
        });
    });
}

// Serve static files
function serveStaticFile(res, filePath) {
    const ext = path.extname(filePath);
    const contentType = mimeTypes[ext] || 'application/octet-stream';
    
    fs.readFile(filePath, (err, content) => {
        if (err) {
            res.writeHead(404);
            res.end('File not found');
            return;
        }
        res.writeHead(200, { 'Content-Type': contentType });
        res.end(content);
    });
}

// API endpoint for stock data
async function handleStockApi(req, res, url) {
    const symbol = url.searchParams.get('symbol');
    const timeframe = url.searchParams.get('timeframe') || '1wk';
    const interval = url.searchParams.get('interval') || '1h';
    
    if (!symbol) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Symbol parameter is required' }));
        return;
    }
    
    try {
        const data = await fetchFromYahoo(symbol.toUpperCase(), timeframe, interval);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(data));
    } catch (err) {
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: err.message }));
    }
}

// Create HTTP server
const server = http.createServer(async (req, res) => {
    // Enable CORS
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    
    if (req.method === 'OPTIONS') {
        res.writeHead(200);
        res.end();
        return;
    }
    
    const url = new URL(req.url, `http://localhost:${PORT}`);
    
    // API endpoint
    if (url.pathname === '/api/stock') {
        await handleStockApi(req, res, url);
        return;
    }
    
    // Serve static files
    let filePath = url.pathname === '/' ? '/index.html' : url.pathname;
    filePath = path.join(__dirname, filePath);
    
    // Security: prevent directory traversal
    if (!filePath.startsWith(__dirname)) {
        res.writeHead(403);
        res.end('Forbidden');
        return;
    }
    
    serveStaticFile(res, filePath);
});

server.listen(PORT, '0.0.0.0', () => {
    console.log(`Server running on http://0.0.0.0:${PORT}`);
    console.log(`Accessible on your network at http://<your-ip>:${PORT}`);
});

// Graceful shutdown
process.on('SIGINT', () => {
    console.log('\nShutting down server...');
    server.close(() => {
        process.exit(0);
    });
});