import numpy as np
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, current_user, logout_user
from forms import LoginForm, UploadForm
from local_settings import SECRET_KEY
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy.sql import text
from flask_admin import Admin, expose, AdminIndexView
from flask_admin.contrib.sqla import ModelView
from sqlalchemy.sql.functions import current_timestamp
from sqlalchemy import event
from pytz import timezone
from dateutil import parser
import tempfile
import zipfile
import scoring
import json
import hashlib
import os

base_dir = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
login_manager = LoginManager()
login_manager.init_app(app)
app.secret_key = SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///{host}/{name}'.format(**{
    'host': base_dir,
    'name': 'db.sqlite3'
})
#app.config['FLASK_ADMIN_SWATCH'] = 'United'
db = SQLAlchemy(app)
migrate = Migrate(app, db)


def utc_to_jst(timestring):
    date = parser.parse(
        timestring,
        default=parser.parse('00:00Z')
    ).astimezone(timezone("Asia/Tokyo"))
    return date.strftime("%Y-%m-%d %H:%M")


app.jinja_env.filters['utc_to_jst'] = utc_to_jst


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(256), unique=True,
                        nullable=False)
    print_name = db.Column(db.String(256), unique=False, nullable=False)
    password = db.Column(db.String(256), unique=False, nullable=False)
    is_admin = db.Column(db.Boolean, nullable=False)
    n_submit = db.Column(db.Integer, default=0)
    scores = db.relationship("Score", backref="users")

    def __init__(self, user_id, password, print_name, is_admin=False):
        self.user_id = user_id
        self.password = password
        self.print_name = print_name
        self.is_admin = is_admin

    def __repr__(self):
        return self.user_id

    def get_id(self):
        return (self.user_id)


class Score(db.Model):
    __tablename__ = "scores"
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.TIMESTAMP, server_default=current_timestamp())
    user_primary_key = db.Column(db.Integer, db.ForeignKey('users.id'))
    comment = db.Column(db.String(256), unique=False, nullable=True)
    # Person = db.Column(db.Float, nullable=False)
    Company = db.Column(db.Float, nullable=False)
    City = db.Column(db.Float, nullable=False)
    # Compound = db.Column(db.Float, nullable=False)
    # Airport = db.Column(db.Float, nullable=False)
    Overall = db.Column(db.Float, nullable=False)
    user = db.relationship("User")

    def __init__(self, result_dict):
        self.user_primary_key = result_dict['user_primary_key']
        self.comment = result_dict['comment']
        # self.Person = result_dict['Person.json']
        self.Company = result_dict['Company.json']
        self.City = result_dict['City.json']
        # self.Compound = result_dict['Compound.json']
        # self.Airport = result_dict['Airport.json']
        self.Overall = result_dict['overall']


db.create_all()


@event.listens_for(User.password, 'set', retval=True)
def hash_user_password(target, value, oldvalue, initiator):
    if value != oldvalue:
        return hashlib.md5(value.encode('utf-8')).hexdigest()
    return value


class ScoreView(ModelView):
    def is_accessible(self):
        return current_user.is_admin


class UserView(ModelView):
    column_exclude_list = ['scores']

    def is_accessible(self):
        return current_user.is_admin


class MyAdminIndexView(AdminIndexView):
    @expose('/')
    def index(self):
        if not current_user.is_admin:
            return redirect(url_for('index'))
        return super(MyAdminIndexView, self).index()


# db.create_all()
admin = Admin(app, index_view=MyAdminIndexView(), template_mode='bootstrap3')
admin.add_view(ScoreView(Score, db.session))
admin.add_view(UserView(User, db.session))


@login_manager.user_loader
def user_loader(user_id):
    return db.session.query(User).filter_by(user_id=user_id).first()


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return redirect(url_for('index'))
    elif request.method == 'POST':
        user_id = request.form['user_id']
        password = request.form['password']
        password_md5 = hashlib.md5(password.encode('utf-8')).hexdigest()

        user_info = db.session.query(User).filter_by(user_id=user_id).first()

        if user_info is not None and password_md5 == user_info.password:
            # ログイン成功
            user = user_info
            login_user(user, remember=True)
            return redirect(url_for('index'))

    flash("ログインに失敗しました．", "failed")
    return redirect(url_for('index'))


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/', methods=['GET'])
def index():
    login_form = LoginForm()
    upload_form = UploadForm()
    columns = ['print_name', 'created_at', 'comment',
               'Company', 'City', 'Overall']
    sort_key = 'Overall'
    ascending = False
    sql_text = "select {} from scores as s".format(', '.join(columns)) \
        + " inner join users on s.user_primary_key = users.id " \
        + " where not exists (select 1 from scores as t where s.user_primary_key" \
        + " = t.user_primary_key and s.created_at < t.created_at )" \
        + " order by {} {}".format(sort_key, 'ASC' if ascending else 'DESC')
    results = db.session.execute(sql_text)
    score_table = list(map(dict, results.fetchall()))
    print(score_table[0]['created_at'])

    return render_template(
        './index.html', login_form=login_form, upload_form=upload_form,
        current_user=current_user, score_table=score_table)


@app.route('/history', methods=['GET'])
def get_scores():
    user = request.args.get('user', None)
    columns = ['print_name', 'created_at', 'comment',
               'Company', 'City', 'Overall']
    sql_text = "select {} from scores as s".format(', '.join(columns)) \
        + " inner join users on s.user_primary_key = users.id " \
        + (" where print_name='{}'".format(user) if user is not None else "") \
        + " order by created_at DESC"
    results = db.session.execute(sql_text)
    score_table = list(map(dict, results.fetchall()))
    return jsonify(score_table)


@app.route('/upload', methods=['POST'])
def upload_and_evaluate():
    filenames = {
        'Company.json', 'City.json',
    }
    settings = json.load(open(base_dir + '/data/settings.json', 'r'))
    target_dict = settings['target_dict']
    annotation_dict = settings['annotation_dict']
    upload_form = UploadForm()
    f = upload_form.zip_file.data
    description = upload_form.description.data
    # tmpdirに展開して一番目の要素を返す
    with tempfile.TemporaryDirectory() as td:
        with zipfile.ZipFile(f) as existing_zip:
            fnames = existing_zip.namelist()
            result = {}

            for fname in fnames:
                basename = os.path.basename(fname)
                if basename in filenames:
                    try:
                        submit_data = [
                            json.loads(line) for line in
                            existing_zip.open(fname, 'r').readlines()
                        ]
                        annotation_path = os.path.join(
                            base_dir, annotation_dict[basename]
                        )
                        target = target_dict[basename]
                        score_dict = scoring.get_score(
                            answer=annotation_path,
                            result=submit_data,
                            target=target
                        )
                        # 森羅LBと同様，'text_offset' が含まれるデータは 'text' での結果を採用
                        if 'text' in score_dict:
                            f1 = score_dict['text']['micro_ave']['F1']
                        else:
                            f1 = score_dict['html']['micro_ave']['F1']
                        result[basename] = f1
                    except:
                        flash("評価スクリプトが異常終了しました．" +
                              "データのフォーマット等を見直してください．", "failed")
                        return redirect(url_for('index'))
                else:
                    continue

            if set(result.keys()) != filenames:
                flash("ファイル構成が正しくありません", "failed")
                return redirect(url_for('index'))

    result['overall'] = np.mean(list(result.values()))
    result['user_primary_key'] = current_user.id
    result['comment'] = str(description)
    score_record = Score(result)
    db.session.add(score_record)
    user_record = db.session.query(User).filter_by(id=current_user.id).first()
    user_record.n_submit += 1
    db.session.commit()
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8001, debug=False)
