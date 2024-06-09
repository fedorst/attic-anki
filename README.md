# Demonstration
![](https://github.com/fedorst/attic-anki/blob/main/app_recording.gif)

# Running the textual app
1. Create python venv `python -m venv .venv`
2. Activate venv `source .venv//bin/activate`
3. Install `requirements.txt` into it: `pip install -r requirements.txt`
4. Navigate to `app`
5. Run `textual run app.py` or `textual run app.py debug` to run it in debug mode.
If you want to reset your progress, delete `user_data.parquet`

# reproducing the data generation
See the README in `notebooks/`
