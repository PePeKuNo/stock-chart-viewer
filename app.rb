require 'sinatra/base'
require 'json'
require 'net/http'
require 'uri'
require 'cgi'

class StockApp < Sinatra::Base
  configure do
    set :bind, '0.0.0.0'
    set :port, ENV.fetch('PORT', 3000)
    set :public_folder, File.dirname(__FILE__)
  end

  YAHOO_BASE = 'https://query1.finance.yahoo.com/v8/finance/chart/'.freeze

  RANGE_MAP = {
    '1d'  => { range: '1d',  interval: '5m'  },
    '5d'  => { range: '5d',  interval: '30m' },
    '1wk' => { range: '1wk', interval: '1h'  },
    '1mo' => { range: '1mo', interval: '1d'  },
    '3mo' => { range: '3mo', interval: '1d'  },
    '1y'  => { range: '1y',  interval: '1d'  },
    '5y'  => { range: '5y',  interval: '1wk' }
  }.freeze

  VALID_INTERVALS = {
    '1d'  => %w[1m 2m 5m 15m 30m 60m 90m],
    '5d'  => %w[5m 15m 30m 60m 90m 1h],
    '1wk' => %w[15m 30m 60m 90m 1h 1d],
    '1mo' => %w[30m 60m 90m 1h 1d],
    '3mo' => %w[1h 1d 1wk],
    '1y'  => %w[1h 1d 1wk 1mo],
    '5y'  => %w[1d 1wk 1mo]
  }.freeze

  before do
    headers 'Access-Control-Allow-Origin' => '*',
            'Access-Control-Allow-Methods' => 'GET, OPTIONS',
            'Access-Control-Allow-Headers' => 'Content-Type'
  end

  options '*' do
    200
  end

  get '/api/stock' do
    content_type :json

    symbol = params[:symbol]&.upcase&.strip
    timeframe = params[:timeframe] || '1wk'
    interval = params[:interval]&.strip

    halt 400, { error: 'Symbol parameter is required' }.to_json if symbol.nil? || symbol.empty?

    config = RANGE_MAP[timeframe] || RANGE_MAP['1wk']
    yahoo_interval = interval || config[:interval]

    unless VALID_INTERVALS[config[:range]].include?(yahoo_interval)
      yahoo_interval = config[:interval]
    end

    url = "#{YAHOO_BASE}#{symbol}?range=#{config[:range]}&interval=#{yahoo_interval}&includePrePost=false"

    begin
      uri = URI(url)
      req = Net::HTTP::Get.new(uri)
      req['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

      response = Net::HTTP.start(uri.hostname, uri.port, use_ssl: true, read_timeout: 10) do |http|
        http.request(req)
      end

      data = JSON.parse(response.body)

      if data.dig('chart', 'error')
        halt 404, { error: data.dig('chart', 'error', 'description') || 'Symbol not found' }.to_json
      end

      result = data.dig('chart', 'result', 0)
      halt 404, { error: 'No data available for this symbol' }.to_json unless result&.dig('timestamp')&.any?

      quotes = result.dig('indicators', 'quote', 0)
      meta = result['meta']
      timestamps = result['timestamp']

      prices = timestamps.each_with_index.filter_map do |ts, i|
        next unless %w[open high low close volume].all? { |k| quotes[k]&.at(i) }

        {
          timestamp: ts * 1000,
          open: quotes['open'][i],
          high: quotes['high'][i],
          low: quotes['low'][i],
          close: quotes['close'][i],
          volume: quotes['volume'][i]
        }
      end

      halt 404, { error: 'No valid price data available' }.to_json if prices.empty?

      {
        symbol: meta['symbol'] || symbol,
        name: meta['longName'] || meta['shortName'] || symbol,
        currency: meta['currency'] || 'USD',
        exchange: meta['exchangeName'] || '',
        timeframe: timeframe,
        interval: yahoo_interval,
        prices: prices
      }.to_json

    rescue Net::ReadTimeout, Net::OpenTimeout
      halt 504, { error: 'Request timeout' }.to_json
    rescue JSON::ParserError
      halt 500, { error: 'Failed to parse response' }.to_json
    rescue => e
      halt 500, { error: e.message }.to_json
    end
  end

  get '/' do
    send_file File.join(settings.public_folder, 'index.html')
  end

  run! if app_file == $0
end