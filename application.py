import os

from flask import Flask, render_template, session, request
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))


@app.route("/")
def index():
    return render_template("default.html")

@app.route("/register", methods=["GET","POST"])
def register():

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirm = request.form.get("confirm")

        if username is None:
            return render_template("error_R.html", message="You must provide an username")
        elif db.execute("SELECT * FROM users WHERE username = :username", {"username":username}).rowcount > 0:
            return render_template("error_R.html", message="Username already exists")
        elif password is None:
            return render_template("error_R.html", message="You must provide a password")
        elif confirm != password:
            return render_template("error_R.html", message="Passwords do not match")

        hashedPassword = generate_password_hash(request.form.get("password"), method='pbkdf2:sha256', salt_length=8)
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)", {"username":username, "hash":hashedPassword})
        db.commit()

        return redirect("/login")

    else:
        return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirm = request.form.get("confirm")
    
    if username is None:
        return render_template("error_L.html", message="Please enter your username")
    elif password is None:
        return render_template("error_L.html", message="Please enter your password")

    result = db.execute("SELECT * FROM users WHERE username = :username", {"username":username}).fetchone()

    if result is None:
        return render_template("error_L.html", message="Invalid username/password")
    elif not check_password_hash(result.hash, request.form.get("password")):
        return render_template("error_L.html", message="Wrong password")

    else :
        return render_template("login.html")

@app.route("/search")
def search():
    return render_template("search.html")

@app.route("/results")
def results():
    query = request.form.get("book")
    
    if query is None:
        return render_template("error_S.html", message="You must enter something")

    search = "%" + query + "%"
    result = db.execute("SELECT isbn, title, author FROM books WHERE isbn LIKE :search OR title LIKE :search OR author LIKE :search", {"search":search})

    if result.rowcount == 0:
        return render_template("error_S.html", message="Sorry, we can't find your book :(")
    
    books = result.fetchall()
    return render_template("result.html", books=books)

@app.route("/result/<int:isbn>", methods=["GET","POST"])
def result(isbn):
    if request.method == "POST":
        currentUser = session["user_id"]
        
        rating = request.form.get("rating")
        comment = request.form.get("comment")
        
        row = db.execute("SELECT id FROM books WHERE isbn = :isbn", {"isbn": isbn})

        bookId = row.fetchone() # (id,)
        bookId = bookId[0]

        row2 = db.execute("SELECT * FROM reviews WHERE user_id = :user_id AND book_id = :book_id",
                    {"user_id": currentUser,
                     "book_id": bookId})

        if row2.rowcount == 1:
            flash('You already submitted a review for this book', 'warning')
            return redirect("/book/" + isbn)

        rating = int(rating)

        db.execute("INSERT INTO reviews (user_id, book_id, comment, rating) VALUES (:user_id, :book_id, :comment, :rating)", {"user_id": currentUser, "book_id": bookId, "comment": comment, "rating": rating})
        db.commit()

        flash('Review submitted!', 'info')

        return redirect("/result/" + isbn)
    
    else:
        row = db.execute("SELECT isbn, title, author, year FROM books WHERE isbn = :isbn", {"isbn": isbn})
        bookInfo = row.fetchall()

        key = os.getenv("GOODREADS_KEY")
        
        query = requests.get("https://www.goodreads.com/book/review_counts.json",
                params={"key": key, "isbns": isbn})

        response = query.json()
        response = response['books'][0]
        bookInfo.append(response)

        row = db.execute("SELECT id FROM books WHERE isbn = :isbn",
                        {"isbn": isbn})

        book = row.fetchone() # (id,)
        book = book[0]

        results = db.execute("SELECT users.username, comment, rating, to_char(time, 'DD Mon YY - HH24:MI:SS') as time FROM users INNER JOIN reviews ON users.id = reviews.user_id WHERE book_id = :book ORDER BY time", {"book": book})
        reviews = results.fetchall()
        return render_template("book.html", bookInfo=bookInfo, reviews=reviews)

@app.route("/api/<isbn>", methods=['GET'])
def api_call(isbn):
    row = db.execute("SELECT title, author, year, isbn, COUNT(reviews.id) as review_count, AVG(reviews.rating) as average_score FROM books INNER JOIN reviews ON books.id = reviews.book_id WHERE isbn = :isbn GROUP BY title, author, year, isbn", {"isbn": isbn})

    if row.rowcount != 1:
        return jsonify({"Error": "Invalid book ISBN"}), 422
   
    tmp = row.fetchone()
    result = dict(tmp.items())
    result['average_score'] = float('%.2f'%(result['average_score']))
    return jsonify(result)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")
        