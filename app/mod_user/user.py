from flask import current_app as app, Blueprint, request, make_response, render_template, redirect, url_for, Response, \
    flash
from mykobo_py.idenfy.models.requests import AccessTokenRequest
from mykobo_py.identity.models.request import CustomerRequest
from mykobo_py.wallets.models.request import RegisterWalletRequest
from requests import HTTPError

from app.decorators import require_wallet_auth
from app.forms import EmailForm, User
from mykobo_py.identity.utils import kyc_rejected, kyc_passed

bp = Blueprint("user", __name__, url_prefix="/user")
network = "solana"


@bp.route("/dashboard", methods=["GET"])
@require_wallet_auth
def dashboard() -> Response:
    wallet_address = request.wallet_address
    service_token = app.config["IDENTITY_SERVICE_CLIENT"].acquire_token()

    try:
        app.logger.info(f"Attempting to retrieve user profile with wallet address: {wallet_address}")
        wallet_profile_response = app.config["WALLET_SERVICE_CLIENT"].get_wallet_profile(service_token, wallet_address)
        wallet_profile = wallet_profile_response.json()
        try:
            app.logger.debug(f"Wallet registered retrieving user with {wallet_profile["profile_id"]}")
            identity_service_response = app.config[
                "IDENTITY_SERVICE_CLIENT"
            ].get_user_profile(service_token, wallet_profile["profile_id"])

            user_data = identity_service_response.json()
            if user_data.get("suspended_at") or user_data.get("deleted_at"):
                app.logger.info("User is suspended or deleted, presenting contact us...")
                return make_response(
                    render_template(
                        "common/contact.html", topic="About your account"
                    ),
                    200,
                )
            if kyc_rejected(user_data.get("kyc_status")):
                app.logger.info("User rejected, presenting contact us...")
                return make_response(
                    render_template(
                        "common/contact.html", topic="About your verification"
                    ),
                    200,
                )

            return make_response(
                render_template(
                    'user/dashboard.html',
                    wallet_address=wallet_address,
                    user_data=user_data,
                    approved=kyc_passed(user_data.get("kyc_status")),
                    wallet_balance='100.00 EURC',
                    eur_balance='0.00',
                    usd_balance='0.00',
                    usdc_balance='0.00'
                )
            )
        except HTTPError as e:
            app.logger.error("HTTP error: %s", e)
            if e.response.status_code == 404:
                return redirect(url_for("user.register", wallet_address=wallet_address))
    except HTTPError as e:
        if e.response.status_code == 404:
            # Register user first
            return redirect(
                url_for(
                    "user.lobby",
                    network=network,
                    wallet_address=wallet_address
                )
            )
        else:
            app.logger.error(e)

    return make_response(render_template("error/500.html"))


@bp.route("/lobby", methods=["GET", "POST"])
@require_wallet_auth
def lobby():
    wallet_address = request.wallet_address
    form = EmailForm()

    if request.method == "POST":
        if form.validate_on_submit():
            try:
                service_token = app.config["IDENTITY_SERVICE_CLIENT"].acquire_token()
                user_profile = app.config["IDENTITY_SERVICE_CLIENT"].get_profile_by_email(
                    service_token, form.email_address.data
                )
                if user_profile.ok:
                    user_profile = user_profile.json()
                    profile_id = user_profile["id"]
                    # check to see if user has already passed KYC
                    # we know this person, bind the wallet to their profile
                    wallet_register_request = RegisterWalletRequest(
                        public_key=wallet_address,
                        profile_id=profile_id,
                        memo=None,
                        chain=network.upper(),
                    )

                    try:
                        wallet_response = app.config[
                            "WALLET_SERVICE_CLIENT"
                        ].register_wallet(service_token, wallet_register_request)
                        if wallet_response.ok:
                            app.logger.info("Successfully registered user wallet")
                            if kyc_passed(user_profile["kyc_status"]):
                                app.logger.info(
                                    f"User has already passed KYC, redirecting to dashboard..."
                                )
                                return redirect(
                                    url_for(
                                        f"user.dashboard"
                                    )
                                )
                            else:
                                app.logger.info(
                                    "User has not passed KYC, redirecting to KYC process..."
                                )
                                return redirect(
                                    url_for(
                                        "user.kyc",
                                        profile_id=profile_id
                                    )
                                )
                        else:
                            app.logger.error(
                                f"Error registering wallet: {wallet_response.text}"
                            )
                            return make_response(
                                render_template(
                                    "error/500.html",
                                    reason="We had trouble registering your wallet, please contact support (support@mykobo.co)"
                                ),
                                500
                            )

                    except HTTPError as wallet_error:
                        if wallet_error.response.status_code == 400:
                            app.logger.warning(wallet_error)
                        elif wallet_error.response.status_code == 409:
                            app.logger.info(
                                f"Wallet already registered for this user: {wallet_error.response.json()}"
                            )
                            return redirect(url_for("user.kyc", profile_id=profile_id))
                        else:
                            app.logger.error(f"Error registering wallet: {wallet_error}")
                            return make_response(
                                render_template(
                                    "error/500.html",
                                    reason="We had trouble registering your wallet, please contact support (support@mykobo.co)"
                                ),
                                500
                            )

            except HTTPError as e:
                if e.response.status_code == 404:
                    app.logger.info(
                        f"User with email {form.email_address.data} not found, redirecting to registration")
                    return redirect(
                        url_for(
                            "user.register",
                            email_address=form.email_address.data,
                        )
                    )
                else:
                    app.logger.error(f"Error fetching profile with email: {e}")
                    return make_response(
                        render_template(
                            "error/500.html",
                            reason="We had trouble retrieving your profile, please try again later"
                        ),
                        500
                    )
        else:
            app.logger.warning(f"User submitted an invalid form! {form.errors}")
            if form.errors:
                for field, errors in form.errors.items():
                    print(f"{field}: {errors}")
                    flash(f"{field.replace('_', ' ').title()}: {', '.join(errors)}", "danger")

            return make_response(
                render_template(
                    "user/lobby.html",
                    form=form,
                    wallet_address = wallet_address
                ),
                200,
            )

    else:
        return make_response(
            render_template(
                "user/lobby.html",
                form=form,
                wallet_address=wallet_address,
            ),
            200,
        )


@bp.route("/register", methods=["GET", "POST"])
@require_wallet_auth
def register():
    wallet_address = request.wallet_address

    if request.method == "POST":
        form = User(request.form)
        form.country.choices = app.config["COUNTRY_CHOICES"]
        if form.validate_on_submit():
            service_token = app.config["IDENTITY_SERVICE_CLIENT"].acquire_token()
            create_user_request = CustomerRequest(
                id=None,
                account=None,
                first_name=form.first_name.data,
                last_name=form.last_name.data,
                email_address=form.email_address.data,
                additional_name=None,
                address_line_1=form.address_line_1.data,
                address_line_2=form.address_line_2.data,
                mobile_number=None,
                birth_date=None,
                birth_country_code=None,
                id_country_code=form.country.data,
                bank_account_number=form.bank_account_number.data,
                bank_number=form.bank_number.data,
                tax_id=None,
                tax_id_name=None,
                credential_id=service_token.subject_id,
            )
            try:
                identity_response = app.config[
                    "IDENTITY_SERVICE_CLIENT"
                ].create_new_customer(service_token, create_user_request)
                if identity_response.ok:
                    profile_id = identity_response.json()["id"]
                    app.logger.info(
                        f"User created successfully, registering new wallet {wallet_address} with this user id [{profile_id}]"
                    )
                    # now register the user on the wallet service
                    wallet_register_request = RegisterWalletRequest(
                        public_key=wallet_address,
                        profile_id=profile_id,
                        memo=None,
                        chain="STELLAR",
                    )
                    try:
                        wallet_response = app.config[
                            "WALLET_SERVICE_CLIENT"
                        ].register_wallet(service_token, wallet_register_request)
                        if wallet_response.ok:
                            # First check if the user has already passed KYC
                            try:
                                app.logger.info(
                                    f"Checking KYC status for user with profile id {profile_id}"
                                )
                                kyc_check_response = app.config[
                                    "IDENTITY_SERVICE_CLIENT"
                                ].get_user_profile(service_token, profile_id)
                                if kyc_check_response.ok:
                                    if kyc_passed(
                                            kyc_check_response.json().get("kyc_status")
                                    ):
                                        app.logger.info(
                                            "User has already passed KYC, redirecting to dashboard..."
                                        )
                                        return redirect(
                                            url_for(
                                                f"user.dashboard"
                                            )
                                        )
                            except HTTPError as e:
                                app.logger.error(
                                    f"Error checking KYC status: {e.response.json()}"
                                )
                                return make_response(
                                    render_template(
                                        "error/500.html",
                                        reason="We had trouble checking your KYC status, please try again later",
                                    ),
                                    500,
                                )

                            # now kick off the KYC process
                            app.logger.info(
                                "Wallet registered successfully, handing off to kyc provider..."
                            )
                            return redirect(
                                url_for("user.kyc", profile_id=profile_id)
                            )
                        else:
                            app.logger.error(
                                f"Error registering wallet: {wallet_response.text}"
                            )
                    except HTTPError as wallet_error:
                        if wallet_error.response.status_code == 409:
                            app.logger.info(
                                f"Wallet already registered for this user: {wallet_error.response.json()}"
                            )
                            # If the wallet is already registered, we can proceed to KYC
                            return redirect(
                                url_for("user.kyc")
                            )
                        else:
                            app.logger.error(
                                f"Error registering wallet: {wallet_error}"
                            )
                            return make_response(
                                render_template(
                                    "error/500.html",
                                    reason="We had trouble registering your wallet, please contact support (support@mykobo.co)"
                                )
                            )
                else:
                    app.logger.error(
                        f"Error creating user: {identity_response.text}"
                    )
            except Exception as e:
                app.logger.error(f"Error creating user: {e}")
                make_response(render_template(
                    "error/500.html",
                    reason="We could not create your profile please try again a little later"),
                    500
                )
        else:
            app.logger.info("Form invalid")
            if form.errors:
                for field, errors in form.errors.items():
                    flash(f"{field.replace("_", " ").title()}: {', '.join(errors)}", "danger")
    else:
        email_address = request.args.get("email_address")
        form = User()
        form.country.choices = app.config["COUNTRY_CHOICES"]
        form.email_address.data = email_address
    return render_template(
        'user/register.html',
        wallet_address=wallet_address,
        form=form,
    )


@bp.route("/kyc", methods=["GET", "POST"])
@require_wallet_auth
def kyc():
    profile_id = request.args.get("profile_id")
    if profile_id is None:
        return make_response(render_template("error/500.html", reason="Bad request"), 500)
    access_token_request = AccessTokenRequest(
        external_ref=profile_id.split(":")[2],
        success_url=url_for(
            "user.kyc_success",
            _external=True,
            _scheme="https"
        ),
        error_url=url_for("user.kyc_failure", _external=True, _scheme="https"),
        unverified_url=url_for("user.kyc_pending", _external=True, _scheme="https"),
    )
    try:
        initiate_kyc_response = app.config["IDENFY_SERVICE_CLIENT"].initiate_kyc(
            access_token_request
        )

        app.logger.info("Access token retrieved successfully")
        resp = initiate_kyc_response.json()
        return redirect(resp["redirect_url"], 301)

    except HTTPError as access_token_request_error:
        app.logger.error(
            f"Error retrieving access token: {access_token_request_error.response.json()}"
        )

        if "error" in access_token_request_error.response.json():
            reason = access_token_request_error.response.json()["error"]
        elif "message" in access_token_request_error.response.json():
            reason = access_token_request_error.response.json()["message"]
        else:
            reason = access_token_request_error.response.text

        return render_template(
            "error/500.html",
            reason=reason,
        )

@bp.route("/verify_user/success", methods=["GET"])
@require_wallet_auth
def kyc_success():
    app.logger.info("KYC process completed successfully")
    return render_template(
        "user/kyc_success.html"
    )


@bp.route("/verify_user/failure", methods=["GET"])
def kyc_failure():
    app.logger.info("KYC process failed")
    return render_template("user/kyc_failure.html")


@bp.route("/verify_user/pending", methods=["GET"])
def kyc_pending():
    app.logger.info("KYC process still pending")
    return render_template("user/kyc_pending.html")
