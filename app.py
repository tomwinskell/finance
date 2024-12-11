import json
from datetime import datetime
import re

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # get userid from session
    userid = session.get("user_id")

    # use userid to fetch data from database
    stocks = db.execute("SELECT symbol, quantity FROM holdings WHERE userid = ?", userid)
    data = db.execute("SELECT username, cash FROM users WHERE id = ?", userid)

    user = data[0]
    user["sum_of_stocks"] = 0

    # create dict for each of the stocks in portfolio containing all data required for the page
    for stock in stocks:
        temp = lookup(stock["symbol"])
        stock['name'] = temp['name']
        stock['price'] = temp['price']
        stock["value"] = round(stock["quantity"] * stock["price"], 2)
        user["sum_of_stocks"] += stock['value']
    user['sum_of_stocks'] = round(user["sum_of_stocks"], 2)
    user["total_balance"] = round(user['cash'] + user ['sum_of_stocks'], 2)

    # render the page with stocks and user dicts with all data
    return render_template("index.html", stocks=stocks, user=user)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # process post request when user selects buy
    if request.method == "POST":

        # get user information and current holdings
        userid = session.get("user_id")
        user = db.execute("SELECT * FROM users WHERE id = ?", userid)
        stocks = db.execute("SELECT * FROM holdings WHERE userid = ?", userid)

        # get values submitted by user using the form
        symbol = request.form.get("symbol")
        quantity = request.form.get("shares")

        # check if quantity is a digit and positive
        if not bool(re.fullmatch(r'[1-9]\d*', quantity)):
            return apology("quantity error", 400)

        # convert quantity to int
        quantity = int(quantity)

        # lookup the symbol the user requested to buy to get the current price
        data = lookup(symbol)
        if not data:
            return apology("symbol not found", 400)
        price = int(data["price"])
        totalCost = price * quantity

        # iterate over users holdings find match for symbol, get symbol id,
        holdings_data = next((item for item in stocks if item.get('symbol') == symbol), None)
        if holdings_data:
            print(holdings_data)
            symbol_id = holdings_data.get('id', 0)
            current_quantity = int(holdings_data.get('quantity', 0))
            new_quantity = quantity + current_quantity


        # get users cash, calculate new cash balance
        cash = int(user[0].get('cash', 0))
        new_cash_balance = cash - totalCost

        # try to update the database with the request to buy
        try:
            if totalCost > cash:
                return apology("insufficient cash available", 400)
            else:
                db.execute("INSERT INTO transactions (symbol, price, quantity, buysell, userid) VALUES (?, ?, ?, 'Buy', ?)", symbol, price, quantity, userid)
                db.execute("UPDATE users SET cash = ? WHERE id = ?", new_cash_balance, userid)

                if holdings_data == None:
                    db.execute("INSERT INTO holdings (symbol, quantity, userid) VALUES (?, ?, ?)", symbol, quantity, userid)
                else:
                    db.execute("UPDATE holdings SET quantity = ? WHERE id = ?", new_quantity, symbol_id)
            return redirect("/")

        except ValueError:
            return apology("error updating database", 400)

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # get userid from session
    userid = session.get("user_id")

    now = datetime.now()
    now = now.strftime("%Y-%m-%d %H:%M")

    # use userid to fetch data from database
    stocks = db.execute("SELECT * FROM transactions WHERE userid = ?", userid)
    user_data = db.execute("SELECT username FROM users WHERE id = ?", userid)
    username = user_data[0]["username"]

    # create dict for each of the stocks in portfolio containing all data required for the page
    for stock in stocks:
        temp = lookup(stock['symbol'])
        stock['name'] = temp['name']

    # render the page with stocks and user dicts with all data
    return render_template("history.html", stocks=stocks, username=username, date=now)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 400)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")

@app.route("/search")
def search():
    q = request.args.get("q")
    if q:
        data = db.execute("SELECT * FROM exchange WHERE symbol LIKE ? OR name LIKE ?", f'%{q}%', f'%{q}%')
    if data:
        return json.dumps(data)

@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "POST":
        symbol = request.form.get("symbol")
        data = lookup(symbol)
        if not data:
            return apology("symbol not found", 400)
        return render_template("quoted.html", name=data["name"], price=data["price"], symbol=symbol.upper())

    else:
        return render_template("quote.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Ensure username was submitted
        if len(username) == 0:
            return apology("must provide username", 400)

        # Ensure password was submitted and confirmation matches
        if not password and confirmation:
            return apology("must provide password and confirmation", 400)

        elif password != confirmation:
            return apology("password and confirmation must match", 400)

        # Hash password
        hash = generate_password_hash(password)

        # Try to insert values into database, if user already exists render apology
        try:
            db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", username, hash)
        except ValueError:
            return apology("username already exists", 400)

        # Redirect to login page
        return redirect("/login")

    # User made GET request to register page, render register template
    else:
        return render_template("register.html")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # get user information and current holdings
    userid = session.get("user_id")
    user = db.execute("SELECT * FROM users WHERE id = ?", userid)
    stocks = db.execute("SELECT symbol, quantity, id FROM holdings WHERE userid = ?", userid)

    if request.method == "POST":

        # get symbol to sell from user input, check if valid
        symbol = request.form.get("symbol")
        lookup_data = lookup(symbol)
        if not lookup_data:
            return apology("invalid symbol selected", 400)

        # get latest price for symbol to sell
        price = int(lookup_data.get('price', 0))  # Default to 0 if 'price' key is missing

        # get num shares to sell, check if quantity is a digit and positive
        shares_to_sell = request.form.get("shares")
        if not bool(re.fullmatch(r'[1-9]\d*', shares_to_sell)):
            return apology("quantity must be positive whole number", 400)
        shares_to_sell = int(shares_to_sell)

        # get num shares held, calculate shares remaining after sale
        symbol_data = next((item for item in stocks if item.get('symbol') == symbol), None)
        shares_held = int(symbol_data.get('quantity', 0))
        shares_remaining = shares_held - shares_to_sell

        # get cash amount, calculate profit, calculate new cash balance
        cash = int(user[0].get('cash', 0))
        profit = price * shares_to_sell
        new_cash_balance = cash + profit

        # update records in database
        try:
            if shares_to_sell > shares_held:
                return apology("not enough shares to sell", 400)
            else:
                db.execute("INSERT INTO transactions (symbol, price, quantity, buysell, userid) VALUES (?, ?, ?, 'Sell', ?)", symbol, price, shares_to_sell, userid)
                db.execute("UPDATE users SET cash = ? WHERE id = ?", new_cash_balance, userid)
                if shares_to_sell == shares_held:
                    db.execute("DELETE FROM holdings WHERE symbol = ?", symbol)
                elif shares_to_sell < shares_held:
                    db.execute("UPDATE holdings SET quantity = ? WHERE symbol = ?", shares_remaining, symbol)
                return redirect('/')
        except ValueError:
            return apology("error updating database", 400)

    # get request render sell.html
    else:
        return render_template("sell.html", stocks=stocks)
