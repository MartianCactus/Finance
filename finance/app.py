import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloadedD
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


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

    current_user = session["user_id"]

    #Finding info about user
    info_from_ownership = db.execute("SELECT stock_quote, amount FROM ownership WHERE user_id=?", current_user)
    info_about_cur_price = []

    #Finding current price of each stock owned by user
    for row in info_from_ownership:
        stinfo = lookup(row['stock_quote'])
        price = stinfo['price']
        info_about_cur_price.append(float(price))

    for i in range(len(info_from_ownership)):
        info_from_ownership[i]['price'] = info_about_cur_price[i]

    #Finding current cash
    cash_list = db.execute("SELECT cash FROM users WHERE username=?", current_user)
    cash_dict = cash_list[0]
    cash = float(cash_dict['cash'])

    #Finding total cash
    total_cash = 0
    for row in info_from_ownership:
        total_cash = total_cash + (row['amount'] * row['price'])

    total_cash = total_cash + cash

    return render_template("index.html", own=info_from_ownership, cash=usd(round(cash, 2)), total=usd(round(total_cash, 2)))

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")

    if request.method == "POST":

        #Check if input is valid
        quote = request.form.get("symbol")
        shares = request.form.get("shares")
        stinfo = lookup(quote)

        if not stinfo:
            return apology("STOCK NOT FOUND")

        try:
            shares = int(shares)
        except ValueError:
             return apology("INVALID NUMBER OF SHARES")

        if shares <= 0:
            return apology("INVALID NUMBER OF SHARES")

        #Identify current user
        current_user = session["user_id"]

        #Converting stock quote to uppercase
        quote = quote.upper()

        #Check if user has enough cash to buy the shares
        cur_price = stinfo["price"]
        moni = cur_price * shares

        moni_list = db.execute("SELECT cash FROM users WHERE username=?", current_user)
        moni_in_hand1 = moni_list[0]
        moni_in_hand = moni_in_hand1["cash"]

        if moni_in_hand < moni:
            return apology("YOU BROKE")

        else:
            #Update Ownership to reflect purchase: Create new field in table / update existing field
            alr_own_or_not = db.execute("SELECT amount FROM ownership WHERE user_id=? AND stock_quote=?", current_user, quote)

            if len(alr_own_or_not) == 0:
                add_new_row = db.execute("INSERT INTO ownership (user_id, stock_quote, amount) VALUES(?, ?, ?)", current_user, quote, shares)
            else:
                update_existing_row = db.execute("UPDATE ownership SET amount =amount+? WHERE user_id=? AND stock_quote=?", shares, current_user, quote)

            #Update History to show the new transaction
            now = datetime.now()
            print(now)

            update_history = db.execute("INSERT INTO history (user_id, stock_quote, act, date, time, amount) VALUES(?, ?, ?, ?, ?, ?)", current_user, quote, "buy", now.strftime("%d/%m/%y"), now.strftime("%H:%M:%S"), shares)

            #Update user's cash
            update_cash = db.execute("UPDATE users SET cash = cash-? WHERE username=?", moni, current_user)

            flash('Succesfully bought!')
            #Redirect to index
            return redirect("/")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    current_user = session["user_id"]

    #Retrieve info from history
    info_from_history = db.execute("SELECT * FROM history WHERE user_id=?", current_user)
    return render_template("history.html", info = info_from_history)


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
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["username"]

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
    if request.method == "GET":
        return render_template("quote.html")

    if request.method == "POST":
        symbol = request.form.get("symbol")
        stinfo = lookup(symbol)

        if stinfo:
            name = stinfo["name"]
            price = usd(stinfo["price"])
            sym = stinfo["symbol"]

            return render_template("quoted.html", name=name, price=price, sym=sym)

        else:
            return apology("stock not found", 400)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # Shows registration page
    if request.method == "GET":
        return render_template("register.html")

    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Ensure password was confirmed
        elif not request.form.get("confirmation"):
            return apology("please confirm password", 400)

        # Ensure username is not taken
        un = request.form.get("username")
        rows = db.execute("SELECT * FROM users WHERE username = ?", un)

        if len(rows) != 0:
            return apology("username taken", 400)

        # Ensure passwords match
        pswd = request.form.get("password")
        conf = request.form.get("confirmation")

        if pswd != conf:
            return apology("passwords dont match", 400)

        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", un, generate_password_hash(pswd))

        #Log User In
        session["user_id"] = un

        return redirect("/")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    current_user = session["user_id"]
    if request.method == "GET":
        fields = db.execute("SELECT stock_quote FROM ownership WHERE user_id=?", current_user)
        return render_template("sell.html", fields=fields)

    if request.method == "POST":

        quote = request.form.get("symbol")
        shares = request.form.get("shares")

        #Check if atleast one option was selected
        if not quote:
            return apology("PLEASE SELECT A STOCK", 400)

        #Identify current user
        current_user = session["user_id"]

        #Converting stock quote to uppercase
        quote = quote.upper()

        #Checking is user has shares of the stock
        does_user_have_stock = db.execute("SELECT * FROM Ownership WHERE user_id=? AND stock_quote=?", current_user, quote)
        if not does_user_have_stock:
            return apology("YOU DO NOT HAVE THIS STOCK", 400)

        #Checking if number of shares is a valid integer
        try:
            shares = int(shares)
        except ValueError:
             return apology("INVALID NUMBER OF SHARES", 400)

        if shares <= 0:
            return apology("INVALID NUMBER OF SHARES", 400)

        #Checking if user has enough shares
        amount_user_has = int(does_user_have_stock[0]['amount'])

        if amount_user_has < shares:
            return apology("YOU DO NOT HAVE THIS MANY SHARES", 400)

        remaining_stocks = amount_user_has - shares

        """ If program reaches this part then selling is viable """

        #Updating Ownership
        if remaining_stocks > 0:
            update_ownership = db.execute("UPDATE ownership SET amount =amount-? WHERE user_id=? AND stock_quote=?", shares, current_user, quote)
        elif remaining_stocks == 0:
            delete_ownership = db.execute("DELETE FROM ownership WHERE user_id=? AND stock_quote=?", current_user, quote)

        #Update History to show the new transaction
        now = datetime.now()
        print(now)

        update_history = db.execute("INSERT INTO history (user_id, stock_quote, act, date, time, amount) VALUES(?, ?, ?, ?, ?, ?)", current_user, quote, "sell", now.strftime("%d/%m/%y"), now.strftime("%H:%M:%S"), shares)

        #Update user's cash
        stinfo = lookup(quote)
        cur_price = stinfo["price"]
        moni = cur_price * shares

        update_cash = db.execute("UPDATE users SET cash = cash+? WHERE username=?", moni, current_user)

        flash('Successfully sold!')

        #Redirect to index
        return redirect("/")

# A personal touch - Change of password!
@app.route("/changepswd", methods=["GET", "POST"])
@login_required
def changepswd():
    """Let users change password"""

    current_user = session["user_id"]

    if request.method == "GET":
        return render_template("changepswd.html")

    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("old"):
            return apology("must provide old password", 403)

        # Ensure password was submitted
        elif not request.form.get("new"):
            return apology("must provide new password", 403)

        old_pswd = request.form.get("old")
        new_pswd = request.form.get("new")

        #Ensure old password is correct
        stored_hash = db.execute("SELECT hash FROM users WHERE username=?", current_user)[0]['hash']
        hash_correct = check_password_hash(stored_hash, old_pswd)

        if hash_correct:
            #Change password to new
            new_hash = db.execute("UPDATE users SET hash=? WHERE username=?", generate_password_hash(new_pswd), current_user)
        else:
            return apology("inputted password does not match current password", 403)

        flash("Password changed successfully!")
        return redirect("/")