import os
import json
import datetime
import requests
from flask import Flask, render_template, session, redirect, url_for, flash, request
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, FileField, PasswordField, BooleanField, SelectMultipleField, ValidationError, RadioField, IntegerField
from wtforms.validators import Required, Length, Email, EqualTo
from flask_sqlalchemy import SQLAlchemy
from flask_script import Manager, Shell
from flask_migrate import Migrate, MigrateCommand
from requests.exceptions import HTTPError
import json


# Imports for login management
from flask_login import LoginManager, login_required, logout_user, login_user, UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash


## App setup code
app = Flask(__name__)
app.debug = True
app.use_reloader = True

db = SQLAlchemy(app)
manager = Manager(app)
migrate = Migrate(app, db)
manager.add_command('db', MigrateCommand)

## All app.config values
app.config['SECRET_KEY'] = 'hardtoguessstring'
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get('DATABASE_URL') or "postgresql://postgres:Anhchuc123@localhost/364FINALNTHERESADB"
app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = True
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False



API_KEY = 'AIzaSyDKu6QMgum0qKcNW1BYptCNqFbQJ9wea6U'

login_manager = LoginManager()
login_manager.session_protection = 'strong'
login_manager.login_view = 'login'
login_manager.init_app(app)

user_lists= db.Table('user_lists', db.Column('user_id', db.Integer, db.ForeignKey('User.id')), db.Column('list_id', db.Integer, db.ForeignKey('list.id')))


##### MODELS #####

class User(db.Model, UserMixin):
    __tablename__ = "User"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), unique=True, index=True)
    email = db.Column(db.String(64), unique=True, index=True)
    password_hash = db.Column(db.String(128))

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# one search term can have many places
class Places(db.Model):
    __tablename__ = 'places'
    id = db.Column(db.Integer, primary_key=True)
    business = db.Column(db.String(128))
    location = db.Column(db.String)
    ratings = db.Column(db.Float)
    search_id = db.Column(db.Integer, db.ForeignKey('searchterm.id'))

class SearchTerm(db.Model):
    __tablename__ = 'searchterm'
    id = db.Column(db.Integer, primary_key=True)
    term = db.Column(db.String(32), unique=True)
    places = db.relationship('Places', backref='SearchTerm')

class Reviews(db.Model):
    __tablename__ = 'reviews'
    id = db.Column(db.Integer, primary_key=True)
    placename = db.Column(db.String(200))
    rating = db.Column(db.Integer)
    price = db.Column(db.Integer)
    text_entry = db.Column(db.String(200))

class PlacesList(db.Model):
    __tablename__ = 'list'
    id = db.Column(db.Integer, primary_key=True)
    place_name = db.Column(db.String(64))
    users = db.relationship('User', secondary=user_lists, backref=db.backref('list', lazy='dynamic'), lazy='dynamic')

###### FORMS ######

class UpdateButtonForm(FlaskForm):
    new_place = StringField("What would you like to update the place to?", validators=[Required()])
    submit = SubmitField("Update")


class DeleteButtonForm(FlaskForm):
    submit = SubmitField("Delete")

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[Required(), Length(1,64), Email()])
    password = PasswordField('Password', validators=[Required()])
    remember_me = BooleanField('Keep me logged in')
    submit = SubmitField('Log In')

class RegistrationForm(FlaskForm):
    email = StringField('Email:', validators=[Required(),Length(1,64),Email()])
    username = StringField('Username:',validators=[Required(),Length(1,64)])
    password = PasswordField('Password:',validators=[Required(),EqualTo('password2',message="Passwords must match")])
    password2 = PasswordField("Confirm Password:",validators=[Required()])
    submit = SubmitField('Register User')


    def validate_email(self,field):
        if User.query.filter_by(email=field.data).first():
            raise ValidationError('Email already registered.')

    def validate_username(self,field):
        if User.query.filter_by(username=field.data).first():
            raise ValidationError('Username already taken')

class SearchForm(FlaskForm):
    place = StringField("Please enter a keyword:", validators=[Required()])
    submit = SubmitField()

    def validate_place(self, field):
        if len(field.data.split()) < 1:
            raise ValidationError("You must enter a keyword")


class ReviewForm(FlaskForm):
    placename = StringField("Enter the business you want to review: ", validators=[Required()])
    rating = StringField("Rate the business on a scale of 1-5 (1-bad, 5-great).", validators=[Required()])
    price = StringField('Rate the price on a scale of 1-5 (1-cheap, 5-crazy expensive).', validators=[Required()])
    text_entry = StringField('Comments:')
    submit = SubmitField()

class AddForm(FlaskForm):
    places = StringField("Enter a place to add ", validators=[Required()])
    submit = SubmitField()

    def validate_places(self,field):
        if PlacesList.query.filter_by(place_name=field.data).first():
            raise ValidationError('You"ve already added this place')

##### HELPER FXNS #####

def get_or_create_search(term):
    search_term = SearchTerm.query.filter_by(term=term).first()
    if search_term:
        return search_term

    search_term = SearchTerm(term=term)
    db.session.add(search_term)
    db.session.commit()
    return search_term

def process_place(business, location, ratings, search):
    place = Places.query.filter_by(business=business).first()
    if place:
        return place
    else:
        search = get_or_create_search(search)
        place = Places(business=business, location=location, ratings=ratings,search_id=search.id)
        db.session.add(place)
        db.session.commit()
        return place

def get_or_create_list(place_name):
    listname = PlacesList.query.filter_by(place_name=place_name).first()
    if listname:
        return listname

    listname = PlacesList(place_name=place_name)
    db.session.add(listname)
    db.session.commit()
    return listname

###### VIEW FXNS ######

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

@app.route('/', methods = ['POST', 'GET'])
@login_required
def index():
    return render_template('index.html')

@app.route('/login',methods=["GET","POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user is not None and user.verify_password(form.password.data):
            login_user(user, form.remember_me.data)
            return redirect(request.args.get('next') or url_for('index'))
        flash('Invalid username or password.')
    return render_template('login.html',form=form)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You are now logged out.')
    return redirect(url_for('index'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        user= User(email=form.email.data,username=form.username.data,password=form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('You can now log in')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/enter_review', methods=["GET", "POST"])
@login_required
def review():
    form = ReviewForm()

    if form.validate_on_submit():
        placename = form.placename.data
        rating = form.rating.data
        price = form.price.data
        text_entry = form.text_entry.data

        review = Reviews(placename=placename, rating=rating, price=price, text_entry=text_entry)
        db.session.add(review)
        db.session.commit()
        flash('Review Added!')
        return redirect(url_for('all_reviews'))
    return render_template('review_form.html',form=form)


@app.route('/all_reviews', methods=["GET", "POST"])
@login_required
def all_reviews():
    review = Reviews.query.all()
    return render_template('reviews.html', review=review)

@app.route('/places_search', methods = ["GET", "POST"])
@login_required
def places_search():
    form = SearchForm()
    if form.validate_on_submit():
        place = form.place.data
        search = get_or_create_search(place)
        url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json?location=42.2808,-83.7430&radius=500&types=food&name="+place+"&key="+API_KEY
        data = requests.get(url)
        results = data.text
        response = json.loads(results)
        try:
            name = (response['results'][0]['name'])
            name1 = (response['results'][1]['name'])
            name2 = (response['results'][2]['name'])
        except:
            name = 'No restaurant could be found'
        try:
            rating = (response['results'][0]['rating'])
            rating1 = (response['results'][1]['rating'])
            rating2 = (response['results'][2]['rating'])
        except:
            rating = 'No rating exists'
        try:
            location = (response['results'][0]['vicinity'])
            location1 = (response['results'][1]['vicinity'])
            location2 = (response['results'][2]['vicinity'])
        except:
            location = 'No location exists'

        newname = process_place(business=name, ratings=rating, location=location, search=place)
        newname1 = process_place(business=name1, ratings=rating1, location=location1, search=place)
        newname2 = process_place(business=name2, ratings=rating2, location=location2, search=place)

        response_results = json.loads(data.text)
        return render_template('search_data.html', form=form, data= response_results)
    flash('All fields are required!')

    return render_template('search_data.html', form=form)

@app.route('/all_searches', methods=["GET", "POST"])
@login_required
def all_searches():
    searches = Places.query.all()
    return render_template('all_searches.html', searches=searches)


@app.route('/add_place', methods=["GET", "POST"])
@login_required
def add():
    form=AddForm()
    if form.validate_on_submit():
        places = form.places.data
        additions = get_or_create_list(places)
        return redirect(url_for('all_places'))
        errors = [v for v in form.errors.values()]
        if len(errors) > 0:
            flash("!!!! ERRORS IN FORM SUBMISSION - " + str(errors))
    return render_template('add_form.html', form=form)

@app.route('/all_places', methods=["GET", "POST"])
@login_required
def all_places():
    form = DeleteButtonForm()
    places = PlacesList.query.all()
    return render_template('added_places.html', places=places, form=form)

@app.route('/list/<option>', methods=["GET","POST"])
@login_required
def new_list(option):
    form = UpdateButtonForm()
    places = PlacesList.query.filter_by(place_name=option).first()
    return render_template('update_form.html', places=places, form=form )

@app.route('/update/<name>', methods=["GET", "POST"])
@login_required
def update(name):
    form = UpdateButtonForm()
    if form.validate_on_submit():
        print("form validated")
        new_update = form.new_place.data
        p = PlacesList.query.filter_by(place_name=name).first()
        p.place_name = new_update
        db.session.commit()
        flash("Updated name to: " + p.place_name)
        return redirect(url_for('all_places'))
    return render_template('update.html', name=name, form=form)

@app.route('/delete/<place>', methods=["GET", "POST"])
def delete(place):
    p = PlacesList.query.filter_by(place_name=place).first()
    db.session.delete(p)
    flash("{} Deleted".format(place))
    return redirect(url_for('all_places'))


if __name__ == '__main__':
    db.create_all()
    manager.run()
