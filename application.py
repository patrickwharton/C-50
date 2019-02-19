import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached


@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    cash = db.execute("SELECT cash FROM users WHERE id=:uid", uid=session['user_id'])
    cash = cash[0]['cash']
    data = []
    rows = db.execute("SELECT symbol, sum(amount) FROM transactions WHERE user_id=:uid GROUP BY 1 HAVING sum(amount) > 0 ORDER BY 1",
                      uid=session['user_id'])
    # try:
    #     if buy == "success":
    #         print('Buy Was Success')
    #         # Create some kinda alert saying buy was a success
    #     elif buy =="sale":
    #         print("Sale success")
    # except NameError:
    #     print('NameError')
    total = cash
    for row in rows:
        temp = lookup(row['symbol'])
        temp['amount'] = row['sum(amount)']
        temp['total'] = temp['amount'] * temp['price']
        total += temp["total"]
        data.append(temp)

    return render_template("index.html", cash=cash, data=data, total=total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        stock = lookup(request.form.get("symbol"))
        shares = request.form.get("shares")
        if not stock:
            return apology("Invalid Stock Symbol")
        try:
            shares = int(shares)
        except ValueError:
            return apology(f"You really think you can buy {shares} shares???")
        if shares < 1:
            return apology(f"You really think you can buy {shares} shares???")

        cash = db.execute("SELECT cash FROM users WHERE id=:uid", uid=session['user_id'])
        cash = cash[0]['cash']
        price = stock['price'] * shares

        if price > cash:
            return apology("You're too poor! LOL")

        db.execute("INSERT INTO transactions (user_id, symbol, amount, price_per_share) VALUES (:uid, :symbol, :amount, :pps)",
                   uid=session['user_id'], symbol=stock['symbol'], amount=shares, pps=stock['price'])

        # Update Cash
        new_cash = cash - price
        db.execute("UPDATE users SET cash = :cash WHERE id = :uid", uid=session['user_id'], cash=new_cash)

        return redirect("/?alert=success")
    else:
        return render_template("buy.html")


@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""
    username = request.args.get("username")
    if len(username) < 1:
        return jsonify(False)

    result = db.execute("SELECT username FROM users WHERE username=:username", username=username)
    if not result:
        return jsonify(True)

    return jsonify(False)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    cash = db.execute("SELECT cash FROM users WHERE id=:uid", uid=session['user_id'])
    cash = cash[0]['cash']
    data = []
    #headers=["Transaction ID", "Transaction Type", "Time", "Symbol", "Amount", "Price per Share", "Total"]
    rows = db.execute("SELECT * FROM transactions WHERE user_id=:uid", uid=session['user_id'])

    for row in rows:
        temp = row['amount']
        if temp < 0:
            row['type'] = "Sale"
            row['amount'] = -temp
        else:
            row['type'] = "Purchase"
        row['total'] = row['amount'] * row['price_per_share']

        data.append(row)

    return render_template("history.html", cash=cash, data=data)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

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


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        try:
            session['data']
        except KeyError:
            session['data'] = []
        stock = lookup(request.form.get("symbol"))
        if not stock:
            return apology("Nah m8")
        # Checks for previous lookups and removes old price
        for i in session['data']:
            if i['symbol'] == stock['symbol']:
                session['data'].remove(i)

        session['data'].append(stock)

        if session['data']:
            return render_template("quoted.html", data=session['data'])
        else:
            return apology("Invalid Stock")
    else:
        session['data'] = []
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        elif not request.form.get("confirmation"):
            return apology("must retype password", 400)

        # Check if passwords match
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("Passwords do not match")

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Check if username is taken
        if len(rows) != 0:
            return apology("Username already taken, plaease choose another")

        db.execute("INSERT INTO users (username, hash) VALUES (:username, :password)",
                   username=request.form.get("username"),
                   password=generate_password_hash(request.form.get("password")))

        return redirect("/?alert=registrationsuccess")
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("Please Submit A Stock Symbol")
        stock = lookup(symbol)
        shares = request.form.get("shares")
        if not stock:
            return apology("Invalid Stock Symbol")
        try:
            shares = int(shares)
        except ValueError:
            return apology(f"You really think you can sell {shares} shares???")
        if shares < 1:
            return apology(f"You really think you can sell {shares} shares???")

        rows = db.execute("SELECT sum(amount) FROM transactions WHERE (user_id=:uid AND symbol=:symbol)",
                          uid=session['user_id'], symbol=stock['symbol'])
        current_shares = rows[0]['sum(amount)']

        price = stock['price'] * shares

        if shares > current_shares:
            return apology("You can't sell what you don't have m8")

        db.execute("INSERT INTO transactions (user_id, symbol, amount, price_per_share) VALUES (:uid, :symbol, :amount, :pps)",
                   uid=session['user_id'], symbol=stock['symbol'], amount=-shares, pps=stock['price'])

        # Update Cash
        cash = db.execute("SELECT cash FROM users WHERE id=:uid", uid=session['user_id'])
        cash = cash[0]['cash']
        new_cash = cash + price
        db.execute("UPDATE users SET cash = :cash WHERE id = :uid", uid=session['user_id'], cash=new_cash)

        return redirect("/?alert=salesuccess")
    else:
        shareslist = []
        rows = db.execute("SELECT symbol FROM transactions WHERE (user_id=:uid) GROUP BY 1 HAVING sum(amount) > 0",
                          uid=session['user_id'])
        for row in rows:
            shareslist.append(row['symbol'])
        # if not shareslist:
        #     return redirect("/?alert=nothingtosell")
        return render_template("sell.html", shares=shareslist)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
