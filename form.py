from flask_wtf.form import FlaskForm
from wtforms import StringField, EmailField, PasswordField, SubmitField, TelField, SelectField
from wtforms.validators import DataRequired, EqualTo, Email, ValidationError
from flask_wtf.file import FileField, FileAllowed, FileRequired

class PasswordSize(object):
    def __init__(self, message=None):
        if not message:
            message = "Password must be greater than 8 characters."
        self.message = message
    def __call__(self, form, field):
        if len(field.data) <= 8:
            raise ValidationError(self.message)
        
class PhoneNumberValidator(object):
    def __init__(self, message=None):
        if not message:
            message = "Please enter a valid 10-digit Phone No."
        self.message = message
    def __call__(self, form, field):
        if len(field.data) != 10 or not field.data.isdigit():
            raise ValidationError(self.message)

class SignUpForm(FlaskForm):
    name = StringField(label="Full Name", validators=[DataRequired(message="This is a required field.")])
    email = EmailField(label="Email Address", validators=[DataRequired(message="Please provide an email address."), Email(message="Please enter a valid email address.")])
    password = PasswordField(label="Password", validators=[DataRequired(message="Please enter a password."), PasswordSize()])
    confirm = PasswordField(label="Confirm Password", validators=[DataRequired(message="Please confirm your password."), EqualTo(fieldname="password", message="Passwords must match.")])
    phone = TelField(label="Phone No.", validators=[DataRequired(message="Phone number is required."), PhoneNumberValidator()])
    
    role = SelectField(label="Account Type", validators=[DataRequired(message="Please select an account type.")], choices=[
        ("", "Select Role"),
        ("supplier", "Supplier / Manufacturer"),
        ("officer", "Enforcement Officer")
    ])
    submit = SubmitField("Register")

class LoginForm(FlaskForm):
    email = EmailField(label="Enter Email", validators=[DataRequired(message="Email is required."), Email(message="Please enter a valid email.")])
    password = PasswordField(label="Enter Password", validators=[DataRequired(message="Password is required.")])
    submit = SubmitField("Log In")

class DevLoginForm(FlaskForm):
    email = EmailField(label="Developer Email", validators=[DataRequired(message="Admin email required."), Email()])
    password = PasswordField(label="Password", validators=[DataRequired(message="Password required.")])
    secret_pin = PasswordField(label="System Admin PIN", validators=[DataRequired(message="PIN required for access.")])
    submit = SubmitField("Access Gateway")

class UploadLabelForm(FlaskForm):
    supplier_id = SelectField(label="Assign to Supplier", coerce=int, validators=[DataRequired(message="Please assign this scan to a registered supplier.")])
    product_name = StringField(label="Product Name", validators=[DataRequired(message="Product name is required.")])
    brand = StringField(label="Brand/Manufacturer", validators=[DataRequired(message="Brand name is required.")])
    category = SelectField(label="Product Category", validators=[DataRequired(message="Please select a category.")], choices=[
        ("", "Select Category"),
        ("Food & Beverage", "Food & Beverage"),
        ("Cosmetics", "Cosmetics"),
        ("Electronics", "Electronics"),
        ("Other", "Other")
    ])
    
    # 1st Image: The Label
    label_image = FileField(label="Upload Product Label Image", validators=[
        FileRequired(message="You must upload an image of the label."),
        FileAllowed(['jpg', 'png', 'jpeg', 'webp'], message="Images only! (jpg, png, jpeg, webp)")
    ])
    
    # 2nd Image: The Overall Product
    product_image = FileField(label="Upload Overall Product Image", validators=[
        FileRequired(message="You must upload an image of the product itself."),
        FileAllowed(['jpg', 'png', 'jpeg', 'webp'], message="Images only! (jpg, png, jpeg, webp)")
    ])
    
    submit = SubmitField("Submit for Compliance Check")