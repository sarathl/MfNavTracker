This repository is to track the live NAV (% change compared to previous day) of a mutual fund, primarily for the purpose of getting the (lower) same day NAV if interested in investing in it.

## How to run

Follow one of the two steps.

1) fork the repo, upload the portfolio constituents file you want to track in *portfolio_files* folder and change the file path in `main.py`
   - portfolio constituents file should contain constituent stocks with their isin and weights in columns "isin" and "weight" respectively.
   - Setup your threshold, TELEGRAM_CHAT_ID, TELEGRAM_TOKEN in your github *settings/secrets/actions*
   - change the workflow yml file in *workflows* if required, otherwise the script runs everyday at 1PM IST. Runs can be tracked in github actions.

2) if you want to run locally, clone the repo
   - install the requirements using `requirements.txt` and trigger `main.py` with the command `python main.py [portfolio constituents file path] [return threshold to notify]`
   - portfolio constituents file should contain constituent stocks with their isin and weights in columns "isin" and "weight" respectively.
   - currently notification is setup only via telegram. *TELEGRAM_TOKEN* and *TELEGRAM_CHAT_ID* have to be provided in *main.py* to get the notification.

### Note: 
- return threshold is used to notify when the MF being tracked has returns <= threshold (to buy more units of the MF at lower same day NAV)
- [Read this to get required things for telegram](https://gist.github.com/nafiesl/4ad622f344cd1dc3bb1ecbe468ff9f8a)
