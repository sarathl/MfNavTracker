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
    chat_id = os.environ.get('TELOGRAM_CHAT_ID')

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
        self.ist_timezone = pytz.timezone('Asia/Kolkata')
        self.threshold = float(os.environ.get('RETURN_THRESHOLD'))
        self.isin_col = 'isin'
        self.weight_col = 'weight'
        self.portfolio = self.read_portfolio(portfolio_file)

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

    def read_portfolio(self, file_path):
        """
        Reads the portfolio file and extract constituents with proper formatting

        Args:
            file_path (str): Path to the PPFAS portfolio Excel file

        Returns:
            pd.DataFrame: Processed portfolio with columns [isin, weight]
        """
        # Read the portfolio file
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        elif file_path.endswith('.xlsx'):
            df = pd.read_excel(file_path)
        else:
            self.logger.error(f"Unsupported portfolio file {file_path}")
            raise ValueError(f"Unsupported portfolio file {file_path}")

        # Check if required columns are present (isin and weight)
        if not (self.isin_col in df.columns and self.weight_col in df.columns):
            missing_cols = [col for col in [self.isin_col, self.weight_col] if col not in df.columns]
            raise ValueError(f"Missing required column {missing_cols}")

        # cleaning up the weights
        df['weight'] = self.process_weights(df['weight'])
        return df

    def process_weights(self, weights_series):
        """Processes weights, removing '%' and converting to numeric values.

        Args:
            weights_series: A pandas Series containing weight strings.

        Returns:
            A pandas Series with processed numeric weights.
        """
        numeric_weights = weights_series.astype(str).str.replace('%', '', regex=False).astype(float)
        return numeric_weights

    def calculate_weighted_price_change(self, portfolio_data):
        """Calculates the weighted sum of percentage change in price difference.

        Args:
          portfolio_data: A pandas DataFrame with 'isin', 'weight' columns.

        Returns:
          The weighted sum of percentage change in price difference.
        """
        weighted_price_change_sum = 0
        weights_sum = 0

        for index, row in portfolio_data.iterrows():
            isin = row['isin']
            try:
                ticker = yf.Ticker(isin)
                company_name = ticker.info['longName']
                history = ticker.history(period="2d")
                if len(history) < 2:  # Check for sufficient history data
                    self.logger.info(f"Insufficient history data for {company_name} - {isin}. Skipping.")
                    continue
                close_price_2d = history['Close'].iloc[-2]
                current_price = history['Close'].iloc[-1]

                price_diff_percentage = ((current_price - close_price_2d) / close_price_2d) * 100

                weight = row['weight']
                weighted_price_change_sum += price_diff_percentage * weight
                weights_sum += weight
                self.logger.info(f"Fetched data for {company_name} - {isin}.")
            except Exception as e:
                self.logger.info(f"Error processing {isin}: {e}")

        if weights_sum > 2:
            return weighted_price_change_sum / 100  # Hardcoded to take care of weights that sum upto 100
        else:
            return weighted_price_change_sum

    def notify_investment_opportunity(self, weighted_return):
        ist_time = datetime.now(pytz.timezone('Asia/Kolkata'))
        message = f"""
        🚨 <b>Investment Opportunity Alert!</b>

        📊 Portfolio down: <b>{weighted_return:.2f}%</b>
        ⏰ Time: {ist_time.strftime('%Y-%m-%d %H:%M:%S %Z')}

        Remember to invest before 2:30 PM IST for same day NAV!
        """
        send_telegram_message(message)
        return

    def check_investment_opportunity(self):
        """
        Check if any holding has fallen more than 5%
        Returns True if investment opportunity exists
        """
        weighted_return = self.calculate_weighted_price_change(self.portfolio)

        # If the live return of portfolio is down below the threshold, raise an investment signal.
        if weighted_return < self.threshold:
            self.logger.info(f"Investment opportunity found! Portfolio down {weighted_return:.2f}%")
            self.notify_investment_opportunity(weighted_return)
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
                self.logger.info("Sending investment signal!")
        except Exception as e:
            self.logger.error(f"Error in portfolio monitoring: {str(e)}")


if __name__ == "__main__":
    # Get the directory where the script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    portfolio_file_path = os.path.join(script_dir, 'portfolio_files', 'PPFCF_portfolio.csv')

    tracker = MutualFundTracker(portfolio_file_path)
    tracker.monitor_portfolio()
