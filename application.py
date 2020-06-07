import os
import requests
import datetime

from flask import Flask, session, request, render_template,  jsonify
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.secret_key = "cualquier cosa 44"
Session(app)

# Set up database
#  engine = create_engine(os.getenv("DATABASE_URL"))
engine = create_engine("postgres://rjlbgyeyhkhyxi:483e9ece5dafb5a03f57a97bfb7c09dba5c2740c89cd6ca68ab5ef278048cb81@ec2-3-216-129-140.compute-1.amazonaws.com:5432/d7dfr6g5lij9ep")
db = scoped_session(sessionmaker(bind=engine))


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    alert = ""
    alert1 = ""
    username = ""
    firstname = ""
    lastname = ""
    if request.method == "POST":
        va = True
        firstname = request.form.get("firstname")
        lastname = request.form.get("lastname")
        username = request.form.get("username")
        password1 = request.form.get("password1")
        password2 = request.form.get("password2")
        if db.execute("SELECT * FROM users WHERE userid = :userid", {"userid": username}).rowcount != 0:
           alert = "User already exists"
           va = False
        if password1 != password2:
           alert1 = "passwords don't match"
           va = False
        if va:
           # we need to hash de password in order to record to de database
           db.execute("INSERT INTO users (userid, firstname, lastname, password) VALUES (:userid, :firstname, :lastname, :password)",
                      {"userid": username, "firstname": firstname, "lastname": lastname, "password": password1})
           db.commit()
           return render_template("success.html")
    return render_template("register.html", alert=alert, alert1=alert1, firstname=firstname, lastname=lastname, username=username)

@app.route("/login", methods=["GET", "POST"])
def login():
    alert = ""
    if session.get("username") is None:
       session["username"] = ""
    if request.method == "POST":
        va = True
        session["username"] = request.form.get("username")
        password = request.form.get("password")
        if db.execute("SELECT * FROM users WHERE userid = :userid and password = :password", {"userid": session["username"],"password": password}).rowcount == 0:
           alert = "Incorrect username or password"
           app.logger.info('NO va')
           va = False
        if va:
           result = db.execute("SELECT * FROM users WHERE userid = :userid and password = :password", {
                            "userid": session["username"], "password": password}).fetchone()
           session["firstname"] = result.firstname
           return render_template("search.html", alert="", username=session["username"], firstname=result.firstname)
           
    return render_template("login.html", alert=alert, username=session["username"])

@app.route("/search", methods=["POST"])
def search():    
    if session.get("username") is None:
       return render_template("index.html")
    alert = ""
    books=[]
    searchtext=request.form.get("searchtext")
    search="%"+searchtext+"%"

    if request.method == "POST":
        if db.execute("SELECT * FROM books WHERE author like :author or isbn like :isbn or title like :title",{"author":search, "isbn":search, "title":search}).rowcount == 0:
           alert = "No results found. Change search criteria."
        else:
           books = db.execute("SELECT * FROM books WHERE author like :author or isbn like :isbn or title like :title",{"author":search, "isbn":search, "title":search}).fetchall()
    return render_template("search.html", alert=alert, books=books, searchtext=searchtext,username=session["username"],firstname=session["firstname"])
    
@app.route('/book/<int:book_id>', methods=["GET", "POST"])
def book(book_id):
    alert = ""
    if session.get("username") is None:
       return render_template("index.html")

    username=session.get("username")       
    if request.method == "POST":
       texto=request.form.get("texto")
       select = request.form.get('sel1')
       
       if texto != "":
          if db.execute("SELECT * FROM reviews WHERE book_id=:book_id and userid=:userid",{"book_id":book_id, "userid":username}).rowcount == 0:          
             db.execute("INSERT INTO reviews (book_id, userid, date, text, rating) VALUES (:book_id, :userid, :date, :text, :rating)",
                      {"book_id": book_id, "userid": username, "date": datetime.datetime.now(), "text": texto, "rating": select[:1]})
             db.commit()
             alert = "Review published. Thank you."
          else:
             alert = "Only one review is allowed per user." 
    book = db.execute("SELECT * FROM books WHERE id = :id", {"id": book_id}).fetchone()
    if book is None:
        return render_template("error.html", message="No such book.") 

    reviewed=db.execute("SELECT * FROM reviews WHERE book_id=:book_id and userid=:userid",{"book_id":book_id, "userid":username}).rowcount
    rating_avg=db.execute("SELECT avg(rating) as rating FROM reviews WHERE book_id=:book_id",{"book_id":book_id}).fetchone().rating
    
    if rating_avg is None: rating_avg=0
    reviews = db.execute("select a.*,concat(b.firstname,' ',b.lastname) as nombre from reviews a inner join users b on a.userid=b.userid WHERE book_id = :id", {"id": book_id}).fetchall()
    
    res = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": "uncSCH2A0dkZmozzsS1acA", "isbns": book.isbn})
    
    data = res.json()
    gr_rating_avg= data["books"][0]["average_rating"]
    gr_ratings_count='{:5d}'.format(data["books"][0]["ratings_count"])

    return render_template("book.html",book=book, alert=alert, rating_avg=rating_avg, gr_rating_avg=gr_rating_avg, gr_ratings_count=gr_ratings_count,reviewed=reviewed, reviews=reviews, username=session["username"])
   

@app.route("/logout")
def logout():
    session.pop("username")
    return render_template("index.html")



@app.route("/api/books/<string:book_isbn>")
def book_api(book_isbn):
    """Return details about a book."""

    # Make sure book exists
    book =  db.execute("SELECT * FROM books WHERE isbn=:isbn",{"isbn":book_isbn}).fetchone()
    if book is None:
       return jsonify({"error": "Invalid book_ISBN"}), 422

    rev =  db.execute("SELECT count(*) as review_count,avg(rating) as average_score FROM reviews WHERE book_id=:book_id",{"book_id":book.id}).fetchone()
    # Get book info
    if rev is None:
       review_count=0
       average_score=0
    else:
       review_count=rev.review_count
       if rev.average_score is None: average_score=0
       else: average_score='%.1f' % rev.average_score

    return jsonify({
        "title": book.title,
        "author": book.author,
        "year": book.year,
        "isbn": book.isbn,
        "review_count": review_count,
        "average_score": average_score
    })



