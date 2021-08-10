from flask_wtf import FlaskForm
from flask_wtf.file import FileRequired, FileAllowed, FileField
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired


class LoginForm(FlaskForm):
    user_id = StringField('ユーザID', validators=[DataRequired()])
    password = PasswordField('パスワード', validators=[DataRequired()])
    submit = SubmitField('ログイン')


class UploadForm(FlaskForm):
    zip_file = FileField('提出ファイル', validators=[
        FileRequired()
    ])
    description = StringField('簡単な手法説明', validators=[DataRequired()])
    submit = SubmitField('アップロード')
