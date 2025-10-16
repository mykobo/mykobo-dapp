from flask_wtf import FlaskForm
from mykobo_py.business.compliance.countries import WHITELISTED_COUNTRIES
from schwifty import IBAN, BIC
from wtforms import StringField, EmailField, SelectField, HiddenField
from wtforms.validators import DataRequired, Email, ValidationError

class EmailForm(FlaskForm):
    email_address = EmailField(
        "Email Address",
        id="email",
        validators=[DataRequired(), Email()],
        description="Email address",
    )



class User(FlaskForm):
    provided_choices = []
    first_name = StringField(
        "First Name",
        validators=[DataRequired()],
        description="First Name as it appears on your ID",
    )
    last_name = StringField(
        "Last Name",
        validators=[DataRequired()],
        description="Last Name as it appears on your ID",
    )
    email_address = EmailField(
        "Email",
        id="email",
        validators=[DataRequired(), Email()],
        description="Email address",
    )
    bank_account_number = StringField(
        "Bank Account Number",
        validators=[DataRequired(), ],
        description="Bank Account Number/IBAN, we will send your funds here for withdrawals",
    )
    bank_number = StringField(
        "Bank (BIC/SWIFT) Number",
        validators=[DataRequired()],
        description="Bank (BIC/SWIFT) number",
    )
    address_line_1 = StringField(
        "First Line of Address",
        validators=[DataRequired()],
        description="First line of your address (e.g., street name and number)",
    )
    address_line_2 = StringField(
        "City",
        validators=[DataRequired()],
        description="City of your residence",
    )
    country = SelectField('Country', description="Country of residence", choices=provided_choices, validate_choice=False)
    token = HiddenField("token", validators=[DataRequired()])


    @staticmethod
    def validate_bank_account_number(field):
        iban = IBAN(field.data, allow_invalid=True)
        if not iban.is_valid:
            raise ValidationError("A valid IBAN is required.")

        if iban.country_code not in WHITELISTED_COUNTRIES:
            raise ValidationError("Unfortunately, we do not support IBANs from your country. Please contact support for more information.")

    @staticmethod
    def validate_bank_number(field):
        bic = BIC(field.data, allow_invalid=True)
        if not bic.is_valid:
            raise ValidationError("A valid BIC/SWIFT number is required.")