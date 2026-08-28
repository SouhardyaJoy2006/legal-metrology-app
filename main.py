import json
from flask import Flask, render_template, redirect, flash, abort, url_for, request, send_file
from flask_bootstrap import Bootstrap5
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, Text, ForeignKey
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import sys
from pathlib import Path

# Add PS_108 to sys.path for importing bis_rag module.
# In this repo PS_108 lives as a sibling folder at the project root
# (alongside main.py), so parent (not parent.parent) is correct here.
_ps108_path = Path(__file__).parent / "PS_108"
if _ps108_path.exists() and str(_ps108_path) not in sys.path:
    sys.path.insert(0, str(_ps108_path))

from dotenv import load_dotenv
from time import time
from fpdf import FPDF

load_dotenv(".env")

# Our Developer Emails
DEVELOPER_EMAILS = [
    email.strip().lower() 
    for email in os.environ.get("DEVELOPER_EMAILS", "").split(",") if email.strip()
]

from form import SignUpForm, LoginForm, UploadLabelForm, DevLoginForm
from ai_services import run_compliance_check

# ------ Defining Database ------ #
class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

# ------ User DataBase -------- #
class User(Base, UserMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    email: Mapped[str] = mapped_column(String, unique=True)
    password: Mapped[str] = mapped_column(String)
    phone: Mapped[str] = mapped_column(String, unique=True)
    role: Mapped[str] = mapped_column(String) # 'supplier', 'officer', 'developer'

# -------- Scan & Compliance DataBase ------- #
class LabelScan(Base):
    __tablename__ = "label_scans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    supplier_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    officer_id: Mapped[int] = mapped_column(ForeignKey("users.id")) 
    
    product_name: Mapped[str] = mapped_column(String)
    brand: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String)  # supplier/officer-declared category
    ai_category: Mapped[str] = mapped_column(String, nullable=True)  # CLIP-predicted category
    
    # --- Updated Image Columns --- #
    image_filename: Mapped[str] = mapped_column(String) # The Label
    product_image_filename: Mapped[str] = mapped_column(String) # The Overall Product
    result_image: Mapped[str] = mapped_column(String, nullable=True) # AI Output
    
    status: Mapped[str] = mapped_column(String, default="Pending Analysis")
    compliance_report: Mapped[str] = mapped_column(Text, nullable=True)
    
    supplier: Mapped["User"] = relationship(foreign_keys=[supplier_id])
    officer: Mapped["User"] = relationship(foreign_keys=[officer_id])

# ------ App Configuration ------ #
app = Flask(__name__)
Bootstrap5(app)
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY", "fallback_secret_key")

# --- Database URI ---
# On Vercel (or anywhere else with no persistent disk), set TURSO_DATABASE_URL
# and TURSO_AUTH_TOKEN (from `turso db show --url` / `turso db tokens create`)
# to use a remote Turso (libSQL) database instead.
# If those aren't set, falls back to the original local SQLite file —
# unchanged local/dev behavior.
TURSO_DATABASE_URL = os.environ.get("TURSO_DATABASE_URL")
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN")

if TURSO_DATABASE_URL and TURSO_AUTH_TOKEN:
    # TURSO_DATABASE_URL looks like "libsql://<db>-<org>.turso.io"; the
    # SQLAlchemy libSQL dialect just needs "sqlite+" prefixed onto it.
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite+{TURSO_DATABASE_URL}?secure=true"
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "connect_args": {"auth_token": TURSO_AUTH_TOKEN},
    }
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL", "sqlite:///metrology.db"
    )
db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def scan_image_url(db_reference):
    """
    Template helper: `scan.image_filename` / `scan.product_image_filename`
    may now be either a Blob URL (Vercel) or a plain local filename
    (local/dev, unchanged) — this resolves either into a usable <img src>.
    """
    if not db_reference:
        return ""
    if db_reference.startswith("http://") or db_reference.startswith("https://"):
        return db_reference
    return url_for('static', filename='scanned_labels/' + db_reference)


app.jinja_env.globals['scan_image_url'] = scan_image_url

# ----- Folders for Uploads ------- #
# On Vercel the deployed filesystem is read-only except /tmp, and /tmp is
# wiped between invocations, so uploaded images won't persist there unless
# they're also pushed to external storage — see the Vercel Blob helpers
# below. Locally / on a normal server this is unchanged and still persists
# to disk as before.
if os.environ.get("VERCEL"):
    UPLOAD_FOLDER = "/tmp/scanned_labels"
else:
    UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'scanned_labels')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ----- Vercel Blob storage (persistent image storage) ------- #
# If BLOB_READ_WRITE_TOKEN is set (Vercel adds this automatically once you
# connect a Blob store to the project), uploaded images are pushed there so
# they survive between requests. If it's not set (e.g. local dev), images
# just save to UPLOAD_FOLDER as before — nothing else changes.
BLOB_TOKEN = os.environ.get("BLOB_READ_WRITE_TOKEN")
if BLOB_TOKEN:
    import vercel_blob


def save_uploaded_image(file_storage, unique_name):
    """
    Saves an uploaded image both:
      1. to a local path (always) so the AI pipeline, which needs a real
         file path, can read it immediately in this same request, and
      2. to Vercel Blob (if configured) for persistence across requests.

    Returns (db_reference, local_ai_path):
      - db_reference: what gets stored in the DB — a Blob URL if Blob
        storage is configured, otherwise just the local filename (original
        behavior, unchanged).
      - local_ai_path: always a real local file path, for run_compliance_check.
    """
    local_path = os.path.join(UPLOAD_FOLDER, unique_name)
    file_storage.save(local_path)

    if BLOB_TOKEN:
        with open(local_path, "rb") as f:
            resp = vercel_blob.put(unique_name, f.read())
        return resp["url"], local_path

    return unique_name, local_path


def resolve_local_path_for_ai(db_reference, tmp_name):
    """
    Given whatever's stored in the DB (a Blob URL or a local filename),
    returns a local file path the AI pipeline can open. Downloads from
    Blob storage to /tmp if needed.
    """
    if db_reference.startswith("http://") or db_reference.startswith("https://"):
        import requests
        local_path = os.path.join("/tmp", tmp_name)
        resp = requests.get(db_reference, timeout=30)
        resp.raise_for_status()
        with open(local_path, "wb") as f:
            f.write(resp.content)
        return local_path

    return os.path.join(UPLOAD_FOLDER, db_reference)

with app.app_context():
    db.create_all()

# ------ Role-Based Access Decorator ------ #
def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('login'))
            if current_user.role not in roles:
                abort(403) # Forbidden access
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ----- Authentication Routes ------- #
@app.route("/", methods=["GET"])
def home():
    if current_user.is_authenticated:
        if current_user.role == "supplier":
            return redirect(url_for("supplier_dashboard"))
        elif current_user.role == "officer":
            return redirect(url_for("officer_dashboard"))
        elif current_user.role == "developer":
            return redirect(url_for("developer_dashboard"))
    return render_template("index.html")

@app.route("/sign_up", methods=["GET", "POST"])
def sign_up():
    form = SignUpForm()
    if form.validate_on_submit():
        user_email = form.email.data.strip().lower()

        existing_user = db.session.execute(
            db.select(User).where((User.email == user_email) | (User.phone == form.phone.data))
        ).scalar()
        
        if existing_user:
            flash("Email or Phone No. already registered. Please log in.")
            return redirect(url_for("login"))
            
        hashed_password = generate_password_hash(form.password.data, method="pbkdf2:sha256", salt_length=8)
        
        # Override role: If email matches developer email, set role as 'developer'
        assigned_role = "developer" if user_email in DEVELOPER_EMAILS else form.role.data

        new_user = User(
            name=form.name.data,
            email=user_email,
            password=hashed_password,
            phone=form.phone.data,
            role=assigned_role
        )
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for("home"))
        
    return render_template("sign_up.html", form=form)

@app.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.execute(db.select(User).where(User.email == form.email.data)).scalar()
        if user and check_password_hash(user.password, form.password.data):
            login_user(user)
            return redirect(url_for("home"))
        else:
            flash("Invalid email or password.")
            
    return render_template("login.html", form=form)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("home"))

# ----- Supplier Routes ------- #
@app.route("/supplier/dashboard", methods=["GET"])
@role_required("supplier")
def supplier_dashboard():
    search_query = request.args.get("search", "")
    
    stmt = db.select(LabelScan).where(LabelScan.supplier_id == current_user.id)
    
    if search_query:
        stmt = stmt.where(LabelScan.product_name.ilike(f"%{search_query}%"))
        
    my_scans = db.session.execute(stmt).scalars().all()
    return render_template("supplier_dashboard.html", scans=my_scans, search_query=search_query)


# ----- Officer Routes ------- #
@app.route("/officer/dashboard")
@role_required("officer")
def officer_dashboard():
    search_query = request.args.get("search", "")
    stmt = db.select(LabelScan).where(LabelScan.officer_id == current_user.id)
    
    if search_query:
        stmt = stmt.where(LabelScan.product_name.ilike(f"%{search_query}%"))
        
    my_scans = db.session.execute(stmt).scalars().all()
    return render_template("officer_dashboard.html", scans=my_scans, search_query=search_query)

@app.route("/officer/upload", methods=["GET", "POST"])
@role_required("officer")
def officer_upload():
    form = UploadLabelForm()
    
    suppliers = db.session.execute(db.select(User).where(User.role == "supplier")).scalars().all()
    form.supplier_id.choices = [(s.id, f"{s.name} ({s.email})") for s in suppliers]
    
    if form.validate_on_submit():
        # Process Label Image
        label_file = form.label_image.data
        label_filename = secure_filename(label_file.filename)
        unique_label_name = f"label_{form.supplier_id.data}_{int(time())}_{label_filename}"
        label_ref, label_path = save_uploaded_image(label_file, unique_label_name)

        # Process Product Image
        prod_file = form.product_image.data
        prod_filename = secure_filename(prod_file.filename)
        unique_prod_name = f"product_{form.supplier_id.data}_{int(time())}_{prod_filename}"
        prod_ref, product_path = save_uploaded_image(prod_file, unique_prod_name)

        # added both to database
        new_scan = LabelScan(
            supplier_id=form.supplier_id.data, 
            officer_id=current_user.id,
            product_name=form.product_name.data,
            brand=form.brand.data,
            category=form.category.data,
            image_filename=label_ref,
            product_image_filename=prod_ref
        )
        db.session.add(new_scan)
        db.session.commit()

        # ----- Run AI pipeline: classify product photo, extract label   -----
        # ----- declarations, and match them against that category's     -----
        # ----- Legal Metrology standards.                                -----
        report = run_compliance_check(product_path, label_path)
        new_scan.compliance_report = json.dumps(report)

        if report.get("classification", {}).get("ok"):
            new_scan.ai_category = report["classification"]["predicted_category"]

        match = report.get("match")
        if match:
            new_scan.status = match["overall_status"]  # "Compliant" / "Non-Compliant"
        else:
            new_scan.status = "Analysis Failed"

        db.session.commit()

        if new_scan.status == "Analysis Failed":
            flash("Images uploaded, but AI analysis could not complete. Check API keys/dependencies and re-run from the report page.")
        else:
            flash(f"Analysis complete — result: {new_scan.status}.")
        return redirect(url_for("view_scan", id=new_scan.id))
        
    return render_template("upload_label.html", form=form)


@app.route("/officer/scan/<int:id>")
@role_required("officer")
def view_scan(id):
    scan = db.session.get(LabelScan, id)
    if not scan or scan.officer_id != current_user.id:
        abort(404)

    report = json.loads(scan.compliance_report) if scan.compliance_report else None
    return render_template("view_scan.html", scan=scan, report=report)


@app.route("/officer/scan/<int:id>/rerun", methods=["POST"])
@role_required("officer")
def rerun_scan(id):
    scan = db.session.get(LabelScan, id)
    if not scan or scan.officer_id != current_user.id:
        abort(404)

    label_path = resolve_local_path_for_ai(scan.image_filename, f"rerun_label_{scan.id}")
    product_path = resolve_local_path_for_ai(scan.product_image_filename, f"rerun_product_{scan.id}")

    report = run_compliance_check(product_path, label_path)
    scan.compliance_report = json.dumps(report)

    if report.get("classification", {}).get("ok"):
        scan.ai_category = report["classification"]["predicted_category"]

    match = report.get("match")
    scan.status = match["overall_status"] if match else "Analysis Failed"

    db.session.commit()
    flash(f"Re-analysis complete — result: {scan.status}.")
    return redirect(url_for("view_scan", id=scan.id))


@app.route("/scan/<int:id>/download_pdf")
@login_required
def download_pdf(id):
    """Generates and serves a PDF report for a specific scan."""
    scan = db.session.get(LabelScan, id)
    if not scan:
        abort(404)

    # Ensure only the assigned supplier or the uploading officer can download it
    if current_user.role == "supplier" and scan.supplier_id != current_user.id:
        abort(403)
    elif current_user.role == "officer" and scan.officer_id != current_user.id:
        abort(403)

    # Parse the JSON report
    report = json.loads(scan.compliance_report) if scan.compliance_report else {}

    # Initialize PDF
    pdf = FPDF()
    pdf.add_page()

    # Title
    pdf.set_font("Helvetica", style="B", size=16)
    pdf.cell(0, 10, txt="Legal Metrology Compliance Report", ln=True, align='C')
    pdf.ln(10)

    # Product Details
    pdf.set_font("Helvetica", style="B", size=12)
    pdf.cell(0, 10, txt="Product Information", ln=True)
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 8, txt=f"Product Name: {scan.product_name}", ln=True)
    pdf.cell(0, 8, txt=f"Brand: {scan.brand}", ln=True)
    pdf.cell(0, 8, txt=f"Supplier: {scan.supplier.name}", ln=True)
    pdf.cell(0, 8, txt=f"Declared Category: {scan.category}", ln=True)
    pdf.cell(0, 8, txt=f"AI Predicted Category: {scan.ai_category or 'N/A'}", ln=True)
    pdf.ln(5)

    # Status
    pdf.set_font("Helvetica", style="B", size=14)
    status_text = f"OVERALL STATUS: {scan.status.upper()}"
    if scan.status == "Compliant":
        pdf.set_text_color(40, 167, 69)  # Green
    else:
        pdf.set_text_color(220, 53, 69)  # Red
    pdf.cell(0, 10, txt=status_text, ln=True)
    pdf.set_text_color(0, 0, 0)  # Reset to black
    pdf.ln(5)

    # ML Match Details
    match_data = report.get("match", {})
    if match_data:
        pdf.set_font("Helvetica", style="B", size=12)
        pdf.cell(0, 10, txt="AI Analysis Details:", ln=True)
        pdf.set_font("Helvetica", size=12)

        # Extract the missing fields dynamically from the AI's "fields" array
        fields = match_data.get("fields", [])
        missing = []
        for field in fields:
            # If the AI marked 'compliant' as False, add the label to our missing list
            if not field.get("compliant", True):
                missing.append(field.get("label", "Unknown Field"))

        # Fallback just in case the AI does output a direct missing_declarations list
        if not missing and "missing_declarations" in match_data:
            missing = match_data.get("missing_declarations", [])

        if missing:
            pdf.cell(0, 8, txt="Missing Mandatory Declarations:", ln=True)
            for item in missing:
                pdf.cell(0, 8, txt=f"  - {item}", ln=True)
        else:
            pdf.cell(0, 8, txt="All required declarations were detected.", ln=True)

    # Save and send the file. UPLOAD_FOLDER already points at /tmp/scanned_labels
    # on Vercel (see above), so this works the same way there as it does locally.
    filename = f"Compliance_Report_{scan.id}.pdf"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    pdf.output(filepath)

    return send_file(filepath, as_attachment=True)

# ----- Developer / Admin Routes ------- #
@app.route("/developer/dashboard")
@role_required("developer")
def developer_dashboard():
    users = db.session.execute(db.select(User)).scalars().all()
    total_scans = db.session.query(LabelScan).count()
    return render_template("developer_dashboard.html", users=users, total_scans=total_scans)

@app.route("/delete_account", methods=["GET", "POST"])
@login_required
def delete_account():
    if request.method == "POST":
        user_to_delete = db.session.get(User, current_user.id)
        
        if user_to_delete.role == "supplier":
            scans_to_delete = db.session.execute(
                db.select(LabelScan).where(LabelScan.supplier_id == user_to_delete.id)
            ).scalars().all()
        elif user_to_delete.role == "officer":
            scans_to_delete = db.session.execute(
                db.select(LabelScan).where(LabelScan.officer_id == user_to_delete.id)
            ).scalars().all()
        else:
            scans_to_delete = []

        # Delete all associated image files for each scan
        for scan in scans_to_delete:
            for filename in [scan.image_filename, scan.product_image_filename, scan.result_image]:
                if not filename:
                    continue
                if filename.startswith("http://") or filename.startswith("https://"):
                    if BLOB_TOKEN:
                        try:
                            vercel_blob.delete(filename)
                        except Exception:
                            pass  # best-effort cleanup, don't block account deletion
                else:
                    filepath = os.path.join(UPLOAD_FOLDER, filename)
                    if os.path.exists(filepath):
                        os.remove(filepath)
            db.session.delete(scan)
                
        db.session.delete(user_to_delete)
        db.session.commit()
        
        logout_user()
        flash("Your account and all associated data have been permanently deleted.")
        return redirect(url_for("home"))
        
    return render_template("delete_account.html")

@app.route("/sih_hidden_gateway", methods=["GET", "POST"])
def hidden_dev_gateway():
    form = DevLoginForm()
    if form.validate_on_submit():
        if form.secret_pin.data != os.environ.get("DEV_PIN"):
            flash("Unauthorized access attempt flagged.")
            return redirect(url_for("home"))
            
        user_email = form.email.data.strip().lower()
        
        user = db.session.execute(db.select(User).where(User.email == user_email)).scalar()
        
        if user:
            if user.role == "developer" and check_password_hash(user.password, form.password.data):
                login_user(user)
                return redirect(url_for("developer_dashboard"))
            else:
                flash("Invalid developer credentials.")
        
        elif user_email in DEVELOPER_EMAILS:
            hashed_pw = generate_password_hash(form.password.data, method="pbkdf2:sha256", salt_length=8)
            new_dev = User(
                name="System Admin",
                email=user_email,
                password=hashed_pw,
                phone="0000000000", 
                role="developer"
            )
            db.session.add(new_dev)
            db.session.commit()
            login_user(new_dev)
            flash("Developer account created and logged in.")
            return redirect(url_for("developer_dashboard"))
        else:
            flash("Email not authorized for developer access.")
            
    return render_template("dev_gateway.html", form=form)


# ----- PS-108 BIS Standards Recommendation Routes ------- #
@app.route("/bis_standards", methods=["GET"])
def bis_standards():
    """Renders the standalone BIS Standards Recommendation Engine webpage."""
    return render_template("bis_standards.html")


@app.route("/api/standards/search", methods=["POST"])
def api_search_standards():
    """REST API endpoint for hybrid semantic retrieval of BIS standards."""
    try:
        data = request.get_json() or {}
        query = (data.get("query") or "").strip()
        top_k = int(data.get("top_k") or 8)
        include_superseded = bool(data.get("include_superseded", True))
        dept_filter = (data.get("department") or "").strip().lower()
        type_filter = (data.get("type_of_standard") or "").strip().lower()

        if not query:
            return {"error": "Query parameter is required."}, 400

        from bis_rag.retrieval import search_standards

        raw_results = search_standards(
            query=query,
            top_k=top_k * 2 if (dept_filter or type_filter) else top_k,
            retrieval_k=30,
            include_superseded=include_superseded,
        )

        filtered = []
        for r in raw_results:
            if dept_filter and dept_filter not in (r.get("department") or "").lower():
                continue
            if type_filter and type_filter not in (r.get("type_of_standard") or "").lower():
                continue
            filtered.append(r)
            if len(filtered) >= top_k:
                break

        return {"query": query, "count": len(filtered), "results": filtered}
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return {"error": str(exc)}, 500


if __name__ == "__main__":
    app.run(debug=True)