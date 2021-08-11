from flask_wtf import FlaskForm
from flask_wtf.file import FileRequired, FileAllowed, FileField
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length


class LoginForm(FlaskForm):
    user_id = StringField('ユーザID', validators=[DataRequired()])
    password = PasswordField('パスワード', validators=[DataRequired()])
    submit = SubmitField('ログイン')


class UploadForm(FlaskForm):
    zip_file = FileField('提出ファイル', validators=[
        FileRequired()
    ])
    description = StringField('簡単な手法説明', validators=[
                              DataRequired(),
                              Length(max=32, message='32文字以下で入力してください')
                              ])
    submit = SubmitField('アップロード')
