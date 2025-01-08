import yfinance as yf
import pandas as pd
from datetime import datetime
import pytz
import logging
import os
import requests


def send_telegram_message(message):
    """Send message via Telegram"""
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')

    if not all([token, chat_id]):
        print("Telegram credentials not found in environment variables")
        return

    api_url = f"https://api.telegram.org/bot{token}/sendMessage"

    try:
        response = requests.post(api_url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"  # Enables HTML formatting
        })

        if response.status_code == 200:
            print("Telegram notification sent successfully")
        else:
            print(f"Failed to send Telegram notification: {response.text}")
    except Exception as e:
        print(f"Error sending Telegram message: {str(e)}")


class MutualFundTracker:
    def __init__(self, portfolio_file):
        """
        Initialize the tracker with a portfolio Excel file
        portfolio_file: Path to Excel file containing portfolio holdings
        """
        self.logger = self.setup_logger()
        self.portfolio = self.read_ppfas_portfolio(portfolio_file)
        self.ist_timezone = pytz.timezone('Asia/Kolkata')
        self.threshold = float(os.environ.get('RETURN_THRESHOLD'))

    def setup_logger(self):
        """Set up logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('fund_tracker.log'),
                logging.StreamHandler()
            ]
        )
        return logging.getLogger(__name__)

    def load_portfolio(self, file_path):
        """
        Load portfolio from Excel file
        Expected columns: Symbol, Exchange, Weight
        """
        try:
            df = pd.read_excel(file_path)
            # Add exchange suffix for Indian stocks
            df['Symbol'] = df.apply(
                lambda x: x['Symbol'] + '.NS' if x['Exchange'] == 'NSE' else x['Symbol'],
                axis=1
            )
            return df
        except Exception as e:
            self.logger.error(f"Error loading portfolio: {str(e)}")
            raise

    def read_ppfas_portfolio(self, file_path):
        """
        Read PPFAS portfolio file and extract constituents with proper formatting
        
        Args:
            file_path (str): Path to the PPFAS portfolio Excel file
            
        Returns:
            pd.DataFrame: Processed portfolio with columns [Symbol, Exchange, Weight]
        """
        # Read the Excel file
        df = pd.read_excel(file_path, skiprows=3)  # Skip the header rows
        
        # Clean up column names
        df.columns = [str(col).strip() for col in df.columns]
        
        # Extract relevant columns
        portfolio = pd.DataFrame()
    
        # Function to extract ticker from ISIN
        def get_exchange_and_symbol(row):
            name = str(row['Name of the Instrument'])
            isin = str(row['ISIN'])
            
            # Skip if not a valid row
            if pd.isna(name) or name == 'nan' or pd.isna(isin) or isin == 'nan':
                return pd.Series({'Symbol': None, 'Exchange': None})
                
            # Handle Indian stocks (ISIN starting with 'IN')
            if isin.startswith('IN'):
                # You might need to maintain a mapping of company names to NSE symbols
                # This is a simplified version
                symbol = name.strip()
                return pd.Series({'Symbol': symbol, 'Exchange': 'NSE'})
                
            # Handle US stocks
            elif isin.startswith('US') or 'nasdaq' in str(row['Industry / Rating']).lower() or 'nyse' in str(row['Industry / Rating']).lower():
                # Extract US ticker - might need adjustment based on actual format
                symbol = name.split('(')[0].strip()
                return pd.Series({'Symbol': symbol, 'Exchange': 'US'})
                
            return pd.Series({'Symbol': None, 'Exchange': None})
    
        # Find the equity section boundaries
        equity_start = df[df['Name of the Instrument'] == 'Equity & Equity related'].index[0]
        money_market_start = df[df['Name of the Instrument'] == 'Money Market Instruments'].index[0]
        # print(f"money_market_start index is {money_market_start}")
        
        # Get only the equity section
        equity_section = df.iloc[equity_start:money_market_start]
        # print(equity_section)

        # Process only equity rows
        # List of strings to identify rows we want to exclude
        exclude_rows = [
            'Sub Total',
            'Total',
            'Equity & Equity related',
            '(a) Listed / awaiting listing on Stock Exchanges',
            '(b) Unlisted',
            'Equity & Equity related Foreign Investments'
        ]
        
        # Filter out summary and header rows
        equity_df = equity_section[
            (equity_section['Name of the Instrument'].notna()) &  # Remove empty rows
            (~equity_section['Name of the Instrument'].str.contains('|'.join(exclude_rows), regex=True, na=False)) &  # Remove summary rows
            (equity_section['ISIN'].notna())  # Ensure ISIN exists
        ]

        # equity_start = df[df['Name of the Instrument'] == 'Equity & Equity related'].index[0]
        # equity_end = df[df['Name of the Instrument'] == 'Total'].index[0]
        # equity_df = df.iloc[equity_start+2:equity_end]  # +2 to skip headers
        
        # Extract required information
        portfolio = equity_df[['Name of the Instrument', 'ISIN', 'Industry / Rating', '% to Net\n Assets']]
        portfolio = portfolio.dropna(subset=['Name of the Instrument', 'ISIN'])
        
        # Get exchange and symbol information
        portfolio[['Symbol', 'Exchange']] = portfolio.apply(get_exchange_and_symbol, axis=1)
        
        # Clean up weight column
        portfolio['Weight'] = portfolio['% to Net\n Assets'].replace('$0.00%', '0').astype(float)
        
        # Select and clean final columns
        final_portfolio = portfolio[['Symbol', 'Exchange', 'Weight']].copy()
        final_portfolio = final_portfolio.dropna(subset=['Symbol'])
        
        tickers_list = []
        for _, row in final_portfolio.iterrows():
            try:
                company_name = row['Symbol'].replace('Oil & Natural Gas Corporation', 'Oil And Natural Gas Corporation').replace('Meta Platforms Registered Shares A', 'Meta Platforms').replace('GMR Airports Infrastructure Limited', 'GMR Airports Ltd').replace('Amazon Com Inc', 'Amazon.com, Inc.')
                s = yf.Search(query=company_name, max_results=5)
                if not s.quotes:
                    s = yf.Search(query=company_name.lower().replace('limited', ''), max_results=5)
                ticker = s.quotes[0]['symbol']
                if row['Exchange'] == 'NSE':
                    for quote in s.quotes:
                        if quote['exchDisp'] in ['NSE', 'BSE']:
                            ticker = quote['symbol']
                            break
            except Exception as e:
                print(f"Error {e} for {row['Symbol']}")
                ticker =  row['Symbol']
            # exchange = row['Exchange']
            # weight = row['Weight']
            tickers_list.append(ticker)
        final_portfolio['Ticker'] = tickers_list

        # # Normalize weights to sum to 1
        # final_portfolio['Weight'] = final_portfolio['Weight'] / final_portfolio['Weight'].sum()
        
        return final_portfolio


    def get_current_prices(self):
        """Get current prices for all holdings"""
        prices = {}
        for symbol in self.portfolio['Ticker']:
            try:
                stock = yf.Ticker(symbol)
                current_price = stock.history(period='1d')['Close'].iloc[-1]
                prices[symbol] = current_price
            except Exception as e:
                self.logger.error(f"Error fetching price for {symbol}: {str(e)}")
        return prices

    def calculate_returns(self):
        """Calculate intraday returns for all holdings"""
        returns = {}
        for symbol in self.portfolio['Ticker']:
            try:
                stock = yf.Ticker(symbol)
                today_data = stock.history(period='1d', interval='1m')
                if not today_data.empty:
                    open_price = today_data['Open'].iloc[0]
                    current_price = today_data['Close'].iloc[-1]
                    intraday_return = ((current_price - open_price) / open_price) * 100
                    returns[symbol] = intraday_return
            except Exception as e:
                self.logger.error(f"Error calculating returns for {symbol}: {str(e)}")
        return returns

    def check_investment_opportunity(self):
        """
        Check if any holding has fallen more than 5%
        Returns True if investment opportunity exists
        """
        returns = self.calculate_returns()
        weighted_return = 0
        
        for symbol, ret in returns.items():
            weight = self.portfolio.loc[self.portfolio['Ticker'] == symbol, 'Weight'].iloc[0]
            weighted_return += ret * weight

        if weighted_return < self.threshold:
            self.logger.info(f"Investment opportunity found! Portfolio down {weighted_return:.2f}%")
            ist_time = datetime.now(pytz.timezone('Asia/Kolkata'))
            message = f"""
            🚨 <b>Investment Opportunity Alert!</b>

            📊 Portfolio down: <b>{weighted_return:.2f}%</b>
            ⏰ Time: {ist_time.strftime('%Y-%m-%d %H:%M:%S %Z')}

            Remember to invest before 2:30 PM IST for same day NAV!
            """
            send_telegram_message(message)
            return True
        self.logger.info(f"Portfolio down {weighted_return:.2f}%")
        return False

    def is_trading_time(self):
        """Check if current time is before 2 PM IST on a weekday"""
        return True
        # current_time = datetime.now(self.ist_timezone)
        # cutoff_time = current_time.replace(hour=14, minute=0, second=0, microsecond=0)
        #
        # # Check if it's a weekday (0 = Monday, 4 = Friday)
        # if current_time.weekday() > 4:
        #     return False
        #
        # return current_time < cutoff_time

    def monitor_portfolio(self):
        """Main monitoring function"""
        if not self.is_trading_time():
            self.logger.info("Outside trading hours or weekend")
            return

        try:
            if self.check_investment_opportunity():
                # Implement your investment logic here
                self.logger.info("Sending investment signal!")
                # You could add notification system here (email, SMS, etc.)
        except Exception as e:
            self.logger.error(f"Error in portfolio monitoring: {str(e)}")


if __name__ == "__main__":
    # Get the directory where the script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    portfolio_file_path = os.path.join(script_dir, 'PPFCF_PPFAS_Monthly_Portfolio_Report_November_30_2024.xls')

    tracker = MutualFundTracker(portfolio_file_path)
    tracker.monitor_portfolio()

