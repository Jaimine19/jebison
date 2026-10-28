from contextlib import closing
from datetime import date, timedelta
import csv
import html
import io
import os
from pathlib import Path
import sqlite3

import bcrypt
import streamlit as st


DB_PATH = Path(os.environ.get("WATER_FACTORY_DB_PATH", Path(__file__).with_name("factory.db")))
DEFAULT_RATES = {250: 5.0, 500: 8.0, 1000: 15.0}
SIZES = {250: "250 ml", 500: "500 ml", 1000: "1 litre"}


def connect_db():
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect_db()) as connection, connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS rates (
                size_ml INTEGER PRIMARY KEY,
                price REAL NOT NULL
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer TEXT NOT NULL,
                size_ml INTEGER NOT NULL,
                qty INTEGER NOT NULL,
                rate REAL NOT NULL,
                paid REAL NOT NULL,
                entry_date TEXT NOT NULL
            )"""
        )
        connection.executemany(
            "INSERT OR IGNORE INTO rates (size_ml, price) VALUES (?, ?)",
            DEFAULT_RATES.items(),
        )


def account_exists():
    with closing(connect_db()) as connection:
        return connection.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None


def password_matches(password, stored_hash):
    encoded_hash = stored_hash.encode("utf-8")
    if encoded_hash.startswith(b"$2y$"):
        encoded_hash = b"$2b$" + encoded_hash[4:]
    return bcrypt.checkpw(password.encode("utf-8")[:72], encoded_hash)


def password_hash(password):
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def fetch_dashboard():
    with closing(connect_db()) as connection:
        rows = connection.execute(
            "SELECT * FROM entries ORDER BY entry_date DESC, id DESC"
        ).fetchall()
        rates = {
            row["size_ml"]: row["price"]
            for row in connection.execute("SELECT size_ml, price FROM rates")
        }

    entries = []
    customers = set()
    collected = 0.0
    outstanding = 0.0
    for row in rows:
        entry = dict(row)
        entry["total"] = entry["qty"] * entry["rate"]
        entry["remaining"] = max(0.0, round(entry["total"] - entry["paid"], 2))
        entry["status"] = (
            "Paid" if entry["remaining"] <= 0
            else "Partial" if entry["paid"] > 0
            else "Due"
        )
        collected += entry["paid"]
        outstanding += entry["remaining"]
        customers.add(entry["customer"].strip().casefold())
        entries.append(entry)
    return entries, rates, collected, outstanding, len(customers)


def format_inr(amount):
    return f"₹{amount:,.2f}"


def size_label(size_ml):
    return SIZES.get(size_ml, f"{size_ml} ml")


def inject_styles():
    if not st.session_state.get("user_id"):
        st.markdown(
            "<style>[data-testid='stSidebar']{display:none}</style>",
            unsafe_allow_html=True,
        )
    st.markdown(
        """
        <style>
        :root {
            --ink:#edf3ef;
            --muted:#9baaa5;
            --green:#c8ed76;
            --green-dark:#10191e;
            --lime:#c8ed76;
            --line:#2c3a3f;
            --paper:#192329;
            --canvas:#0f171b;
        }
        html, body, [class*="css"] { font-family:Inter, "Segoe UI", sans-serif; }
        .stApp { background:var(--canvas); color:var(--ink); }
        [data-testid="stHeader"] { background:rgba(15,23,27,.92); }
        .block-container { max-width:1440px; padding:1.6rem 2.4rem 3.5rem; }
        h1,h2,h3 { color:var(--ink); letter-spacing:-.035em; }
        h1 { font-size:2rem !important; font-weight:750 !important; }
        h2 { font-size:1.25rem !important; font-weight:700 !important; }
        h3 { font-size:1.05rem !important; font-weight:700 !important; }
        p { color:var(--muted); }
        [data-testid="stSidebar"] { background:#111b20; border-right:1px solid #253238; }
        [data-testid="stSidebar"] * { color:#eff6ed; }
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
        [data-testid="stSidebar"] .stCaption { color:#a9beb0 !important; }
        [data-testid="stSidebar"] hr { border-color:rgba(255,255,255,.14); }
        [data-testid="stSidebar"] [data-testid="stRadio"] label {
            border-radius:11px; padding:.3rem .55rem; transition:background .16s ease;
        }
        [data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
            background:rgba(255,255,255,.09);
        }
        [data-testid="stSidebar"] [data-testid="stRadio"] [aria-checked="true"] + div {
            color:var(--lime);
        }
        [data-testid="stSidebar"] [data-testid="stMetric"] {
            background:rgba(255,255,255,.035); border:1px solid rgba(255,255,255,.09);
            border-radius:14px; padding:.7rem .85rem; box-shadow:none;
        }
        [data-testid="stSidebar"] [data-testid="stMetricLabel"] p { color:#a9beb0 !important; }
        [data-testid="stSidebar"] [data-testid="stMetricValue"] { color:#fff; font-size:1.2rem; }
        [data-testid="stMetric"] {
            background:var(--paper); border:1px solid var(--line); border-radius:16px;
            padding:1.05rem 1.15rem; box-shadow:0 8px 26px rgba(0,0,0,.12);
        }
        [data-testid="stMetricLabel"] p { color:var(--muted) !important; font-weight:600; font-size:.82rem; }
        [data-testid="stMetricValue"] { color:var(--ink); font-weight:750; }
        [data-testid="stMetricDelta"] { font-size:.78rem; }
        div[data-testid="stForm"], div[data-testid="stExpander"],
        [data-testid="stVerticalBlockBorderWrapper"] {
            background:var(--paper); border:1px solid var(--line); border-radius:16px;
        }
        div[data-testid="stForm"] { padding:1rem 1.1rem; }
        .stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {
            min-height:2.65rem; border-radius:10px; border:1px solid var(--lime);
            background:var(--lime); color:#17241e; font-weight:700; transition:all .16s ease;
        }
        .stButton > button:hover, .stFormSubmitButton > button:hover,
        .stDownloadButton > button:hover {
            background:#d8f59b; border-color:#d8f59b; color:#17241e;
        }
        .stButton > button, .stFormSubmitButton > button, .stDownloadButton > button,
        .stButton > button *, .stFormSubmitButton > button *, .stDownloadButton > button * {
            color:#17241e !important; opacity:1 !important;
        }
        [data-testid="stSidebar"] .stButton > button {
            background:var(--lime); border-color:var(--lime); color:#17241e;
        }
        [data-testid="stSidebar"] .stButton > button,
        [data-testid="stSidebar"] .stButton > button * {
            color:#17241e !important;
        }
        [data-testid="stSidebar"] .stButton > button:hover {
            background:#d7f59a; border-color:#d7f59a;
        }
        [data-testid="stDownloadButton"] > button {
            background:#202d33; border-color:#35444a; color:#e4ede7;
        }
        [data-testid="stDownloadButton"] > button:hover {
            background:#2b3b40; border-color:#526568; color:#fff;
        }
        [data-testid="stAlert"] {
            background:#202b29; border:1px solid #3a5146; border-radius:12px;
        }
        [data-testid="stAlert"] p { color:#e3ede6; }
        .stTextInput input, .stNumberInput input, .stDateInput input,
        [data-baseweb="select"] > div {
            border-radius:9px !important; background:#202b31 !important; color:var(--ink) !important;
        }
        .stTextInput input, .stNumberInput input, .stDateInput input {
            background:#202b31 !important; color:var(--ink) !important; border-color:#39494e !important;
        }
        [data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:13px; overflow:hidden; }
        [data-testid="stTabs"] [role="tab"] { font-weight:650; }
        .hero {
            position:relative; overflow:hidden; display:flex; align-items:center;
            justify-content:space-between; gap:1.5rem; background:#192720;
            padding:1.8rem 2rem; border-radius:20px; color:#fff; margin:0 0 1rem;
            box-shadow:0 12px 30px rgba(22,59,45,.12);
        }
        .hero:after { content:""; position:absolute; width:230px; height:230px; right:13%; top:-155px;
            border:1px solid rgba(255,255,255,.15); border-radius:50%;
            box-shadow:0 0 0 26px rgba(255,255,255,.035),0 0 0 54px rgba(255,255,255,.025); }
        .hero h2 { color:#fff !important; font-size:1.65rem !important; margin:0 0 .35rem; }
        .hero p { color:#c6d6cb; margin:0; }
        .eyebrow { color:var(--lime) !important; text-transform:uppercase; font-size:.68rem;
            letter-spacing:.14em; font-weight:700; margin-bottom:.55rem !important; }
        .hero-note { position:relative; z-index:1; text-align:right; color:#d7e5d9;
            font-size:.82rem; min-width:140px; }
        .hero-note strong { display:block; font-size:1.05rem; color:#fff; }
        .section-kicker { color:var(--lime); text-transform:uppercase; letter-spacing:.12em;
            font-size:.68rem; font-weight:750; }
        .stCaption { color:var(--muted); }
        .page-heading { margin:.3rem 0 1.1rem; }
        .page-heading h1 { margin:.2rem 0 .35rem; }
        .page-heading p { margin:0; color:var(--muted); }
        .brand-lockup { display:flex; align-items:center; gap:.7rem; font-weight:750; color:var(--ink); }
        .brand-symbol { display:inline-flex; align-items:center; justify-content:center;
            width:40px; height:40px; border-radius:13px; background:var(--lime);
            color:var(--green-dark); font-size:1.2rem; }
        .auth-brand { display:flex; align-items:center; gap:.7rem; font-size:.85rem;
            color:#b5c3bd; letter-spacing:.08em; text-transform:uppercase; font-weight:700; }
        .login-title { margin:.7rem 0 .3rem !important; font-size:1.9rem !important; }
        .login-caption { color:var(--muted); margin:0 0 1.2rem; }
        [data-testid="stRadio"] > div[role="radiogroup"] {
            gap:.45rem; padding:.3rem; background:#111a1f; border:1px solid #2d3b40;
            border-radius:11px;
        }
        [data-testid="stRadio"] > div[role="radiogroup"] label {
            border-radius:8px; padding:.45rem .7rem;
        }
        [data-testid="stRadio"] [role="radiogroup"] [data-testid="stRadioOption"] {
            background:transparent; color:#c1cdc7;
        }
        [data-testid="stRadio"] [role="radiogroup"] [data-testid="stRadioOption"] > div > div:first-child {
            display:none;
        }
        [data-testid="stRadio"] [role="radiogroup"] [data-testid="stRadioOption"] p {
            color:inherit !important;
        }
        [data-testid="stRadio"] [role="radiogroup"] [data-testid="stRadioOption"][data-selected="true"] {
            background:#c8ed76; color:#17241e;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.auth-brand) {
            background:transparent; border:0; box-shadow:none;
        }
        @media (max-width:900px) {
            .block-container{padding:1.15rem 1rem 2rem;}
        }
        @media (max-width:600px) {
            .hero{align-items:flex-start;padding:1.35rem;flex-direction:column;}
            .hero-note{text-align:left;}
            .login-title{font-size:1.65rem !important;}
            h1{font-size:1.65rem !important;}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def show_auth():
    first_account = not account_exists()
    if "auth_mode" not in st.session_state or st.session_state.auth_mode not in (
        "Log in",
        "Create account",
    ):
        st.session_state.auth_mode = "Log in"
    if not first_account:
        st.session_state.auth_mode = "Log in"

    left_space, auth_column, right_space = st.columns([1, 1.25, 1])
    with auth_column:
        with st.container(border=True):
            st.markdown(
                '<div class="auth-brand"><span class="brand-symbol">◉</span>'
                '<span>Clearwater · Owner workspace</span></div>',
                unsafe_allow_html=True,
            )
            if first_account:
                mode = st.radio(
                    "Account access",
                    ["Log in", "Create account"],
                    horizontal=True,
                    label_visibility="collapsed",
                    key="auth_mode",
                )
            else:
                mode = "Log in"

            is_signup = mode == "Create account"
            title = "Create your owner account" if is_signup else "Back in balance."
            caption = (
                "Set up the owner login for this private business ledger."
                if is_signup
                else (
                    "No owner account exists yet. Use Create account during private setup."
                    if first_account
                    else "Sign in to manage your orders, payments and customer balances."
                )
            )
            st.markdown(
                f"""<h1 class="login-title">{title}</h1>
                <p class="login-caption">{caption}</p>""",
                unsafe_allow_html=True,
            )

            if is_signup:
                with st.form("signup_form"):
                    username = st.text_input("Username", placeholder="Choose a username", autocomplete="username")
                    password = st.text_input("Password", type="password", placeholder="At least 8 characters", autocomplete="new-password", max_chars=72)
                    confirm_password = st.text_input("Confirm password", type="password", placeholder="Enter your password again", autocomplete="new-password")
                    submitted = st.form_submit_button("Create owner account", use_container_width=True)
                if submitted:
                    username = username.strip()
                    if not username or len(username) > 80:
                        st.error("Enter a username between 1 and 80 characters.")
                    elif len(password) < 8:
                        st.error("Choose a password with at least 8 characters.")
                    elif len(password.encode("utf-8")) > 72:
                        st.error("Password must be no longer than 72 UTF-8 bytes.")
                    elif password != confirm_password:
                        st.error("Those passwords do not match.")
                    else:
                        created_user_id = None
                        try:
                            with closing(connect_db()) as connection, connection:
                                if connection.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                                    st.error("An owner account already exists. Please sign in.")
                                else:
                                    cursor = connection.execute(
                                        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                                        (username, password_hash(password)),
                                    )
                                    created_user_id = cursor.lastrowid
                        except sqlite3.IntegrityError:
                            st.error("That username is already in use. Please choose another.")
                        if created_user_id is not None:
                            st.session_state.user_id = created_user_id
                            st.session_state.username = username
                            st.rerun()
            else:
                with st.form("login_form"):
                    username = st.text_input("Username", placeholder="Your username", autocomplete="username")
                    password = st.text_input("Password", type="password", placeholder="Your password", autocomplete="current-password", max_chars=72)
                    submitted = st.form_submit_button("Sign in", use_container_width=True)
                if submitted:
                    with closing(connect_db()) as connection:
                        user = connection.execute(
                            "SELECT id, username, password_hash FROM users WHERE username = ?",
                            (username.strip(),),
                        ).fetchone()
                    if user and password_matches(password, user["password_hash"]):
                        st.session_state.user_id = user["id"]
                        st.session_state.username = user["username"]
                        st.rerun()
                    else:
                        st.error("The username or password is incorrect.")


def save_entry(customer, size_ml, quantity, rate, paid, entry_date):
    with closing(connect_db()) as connection, connection:
        connection.execute(
            """INSERT INTO entries (customer, size_ml, qty, rate, paid, entry_date)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (customer.strip(), size_ml, quantity, rate, paid, entry_date.isoformat()),
        )


def add_entry_form(rates, expanded=False):
    with st.expander("＋  Add a customer entry", expanded=expanded):
        with st.form("add_entry_form", clear_on_submit=True):
            customer = st.text_input("Customer or business name", placeholder="e.g. Ramesh Traders")
            left, middle, right = st.columns(3)
            with left:
                size_ml = st.selectbox("Bottle size", options=list(SIZES), format_func=lambda size: SIZES[size])
                quantity = st.number_input("Quantity", min_value=1, step=1, value=1)
            with middle:
                rate = st.number_input("Rate per bottle (₹)", min_value=0.0, step=0.5, value=float(rates.get(size_ml, 0.0)))
                paid = st.number_input("Paid today (₹)", min_value=0.0, step=0.5, value=0.0)
            with right:
                entry_date = st.date_input("Order date", value=date.today())
            submitted = st.form_submit_button("Save entry", use_container_width=True)
        if submitted:
            if not customer.strip():
                st.error("Enter a customer or business name.")
            else:
                save_entry(customer, size_ml, int(quantity), rate, paid, entry_date)
                st.success(f"Entry saved for {customer.strip()}.")
                st.rerun()


def status_badge(status):
    return {"Paid": "● Paid", "Partial": "◐ Partial", "Due": "○ Due"}[status]


def page_heading(kicker, title, description):
    st.markdown(
        f"""<div class="page-heading">
        <p class="section-kicker">{kicker}</p>
        <h1>{title}</h1>
        <p>{description}</p>
        </div>""",
        unsafe_allow_html=True,
    )


def ledger_view(entries):
    page_heading(
        "CUSTOMER RECORDS",
        "Customer ledger",
        "Search orders, check payment status, and record follow-up payments.",
    )
    add_entry_form(fetch_dashboard()[1])
    controls = st.columns([1, 2, 1])
    with controls[0]:
        status_filter = st.selectbox(
            "Payment status",
            ["All", "Outstanding", "Due", "Partial", "Paid"],
            key="ledger_status_filter",
        )
    with controls[1]:
        search = st.text_input("Search customers", placeholder="Search by customer name")
    filtered = [
        entry for entry in entries
        if (
            status_filter == "All"
            or (status_filter == "Outstanding" and entry["remaining"] > 0)
            or entry["status"] == status_filter
        )
        and search.casefold() in entry["customer"].casefold()
    ]
    st.caption(f"Showing {len(filtered):,} {'entry' if len(filtered) == 1 else 'entries'}")
    if filtered:
        table_rows = [
            {
                "Customer": entry["customer"],
                "Date": entry["entry_date"],
                "Product": f"{size_label(entry['size_ml'])} × {entry['qty']}",
                "Total": format_inr(entry["total"]),
                "Paid": format_inr(entry["paid"]),
                "Balance": format_inr(entry["remaining"]),
                "Status": status_badge(entry["status"]),
            }
            for entry in filtered
        ]
        with st.container(border=True):
            st.dataframe(table_rows, use_container_width=True, hide_index=True)
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=table_rows[0].keys())
        writer.writeheader()
        writer.writerows(table_rows)
        st.download_button("Download this ledger as CSV", output.getvalue(), "water-factory-ledger.csv", "text/csv")
        for entry in filtered:
            if entry["remaining"] > 0:
                with st.expander(f"Payment · {entry['customer']} · {format_inr(entry['remaining'])} outstanding"):
                    with st.form(f"payment_{entry['id']}"):
                        amount = st.number_input(
                            "Payment received (₹)",
                            min_value=0.01,
                            max_value=float(entry["remaining"]),
                            step=0.5,
                            key=f"payment_amount_{entry['id']}",
                        )
                        paid_now = st.form_submit_button("Record payment")
                    if paid_now:
                        with closing(connect_db()) as connection, connection:
                            connection.execute(
                                "UPDATE entries SET paid = paid + ? WHERE id = ?",
                                (amount, entry["id"]),
                            )
                        st.success("Payment recorded.")
                        st.rerun()
            if st.session_state.get("confirm_delete_id") == entry["id"]:
                st.warning(f"Delete the ledger entry for {entry['customer']}? This cannot be undone.")
                confirm, cancel = st.columns(2)
                if confirm.button("Delete entry", key=f"delete_confirm_{entry['id']}", type="primary"):
                    with closing(connect_db()) as connection, connection:
                        connection.execute("DELETE FROM entries WHERE id = ?", (entry["id"],))
                    del st.session_state["confirm_delete_id"]
                    st.rerun()
                if cancel.button("Keep entry", key=f"delete_cancel_{entry['id']}"):
                    del st.session_state["confirm_delete_id"]
                    st.rerun()
            elif st.button("Delete entry", key=f"delete_{entry['id']}"):
                st.session_state.confirm_delete_id = entry["id"]
                st.rerun()
    else:
        st.info("No customer entries match these filters. Add an entry to get started.")


def settings_view(rates):
    page_heading(
        "WORKSPACE",
        "Business settings",
        "Manage current bottle prices and maintain your ledger.",
    )
    st.markdown("### Bottle rates")
    st.caption("New rates apply to new orders. Existing orders keep their recorded price.")
    with st.form("rates_form"):
        columns = st.columns(3)
        new_rates = {}
        for column, (size, label) in zip(columns, SIZES.items()):
            with column:
                new_rates[size] = st.number_input(
                    f"{label} · ₹ per bottle",
                    min_value=0.0,
                    step=0.5,
                    value=float(rates.get(size, DEFAULT_RATES[size])),
                    key=f"rate_{size}",
                )
        if st.form_submit_button("Save bottle rates"):
            with closing(connect_db()) as connection, connection:
                connection.executemany(
                    "UPDATE rates SET price = ? WHERE size_ml = ?",
                    [(price, size) for size, price in new_rates.items()],
                )
            st.success("Bottle rates updated.")
            st.rerun()
    st.write("")
    with st.container(border=True):
        st.markdown("### Reset ledger")
        st.caption(
            "Permanently remove every customer entry and restore default bottle rates. "
            "Your owner account will remain."
        )
        if not st.session_state.get("confirm_reset"):
            if st.button("Reset all ledger data"):
                st.session_state.confirm_reset = True
                st.rerun()
        else:
            st.warning("This cannot be undone. Are you sure you want to clear the ledger?")
            confirm, cancel = st.columns(2)
            if confirm.button("Yes, reset everything", type="primary"):
                with closing(connect_db()) as connection, connection:
                    connection.execute("DELETE FROM entries")
                    connection.executemany(
                        "UPDATE rates SET price = ? WHERE size_ml = ?",
                        DEFAULT_RATES.items(),
                    )
                del st.session_state["confirm_reset"]
                st.success("Ledger and rates reset. Your login is unchanged.")
                st.rerun()
            if cancel.button("Cancel"):
                del st.session_state["confirm_reset"]
                st.rerun()


def show_dashboard():
    entries, rates, collected, outstanding, customer_count = fetch_dashboard()
    open_orders = sum(1 for entry in entries if entry["remaining"] > 0)

    with st.sidebar:
        st.markdown(
            '<div style="font:800 1.25rem Manrope,sans-serif;color:#fff;padding:.5rem 0 .25rem">◉ Clearwater</div>',
            unsafe_allow_html=True,
        )
        st.caption("YOUR WATER BUSINESS WORKSPACE")
        st.radio(
            "Workspace",
            ["Overview", "Customer ledger", "New order", "Settings"],
            format_func=lambda page_name: {
                "Overview": "◉  Overview",
                "Customer ledger": "▤  Customer ledger",
                "New order": "＋  New order",
                "Settings": "⚙  Settings",
            }[page_name],
            label_visibility="collapsed",
            key="workspace_page",
        )
        st.divider()
        st.markdown("#### Ledger snapshot")
        st.metric("Outstanding balance", format_inr(outstanding))
        st.caption(f"{open_orders:,} orders still need payment")
        if st.button("Review unpaid balances", use_container_width=True):
            st.session_state.workspace_page = "Customer ledger"
            st.session_state.ledger_status_filter = "Outstanding"
            st.rerun()
        st.caption(f"{len(entries):,} total orders · {customer_count:,} customers")
        st.divider()
        st.markdown(f"**{st.session_state.username}**")
        st.caption("Owner account · Full access")
        if st.button("Sign out", use_container_width=True):
            for key in (
                "user_id",
                "username",
                "confirm_reset",
                "confirm_delete_id",
                "workspace_page",
                "ledger_status_filter",
            ):
                st.session_state.pop(key, None)
            st.rerun()

    page = st.session_state.workspace_page
    if page == "Overview":
        st.markdown(
            f"""<div class="hero"><div>
            <p class="eyebrow">YOUR BUSINESS AT A GLANCE</p>
            <h2>Welcome back, {html.escape(st.session_state.username)}.</h2>
            <p>Here is the latest view of your orders and collections.</p>
            </div><div class="hero-note">TODAY<strong>{date.today().strftime('%d %b %Y')}</strong></div></div>""",
            unsafe_allow_html=True,
        )
        first, second = st.columns(2)
        first.metric("Total collected", format_inr(collected), help="Payments received across all entries")
        second.metric("Outstanding balance", format_inr(outstanding), help="Amount still owed by customers")
        third, fourth = st.columns(2)
        third.metric("Customers", f"{customer_count:,}", help="Unique customer names")
        fourth.metric("Total orders", f"{len(entries):,}", help="All customer orders in this ledger")
        st.write("")
        chart_column, activity_column = st.columns(2, gap="large")
        with chart_column:
            with st.container(border=True):
                st.markdown("### Weekly collections")
                st.caption("Payments received over the last seven days")
                if entries:
                    week = [date.today() - timedelta(days=offset) for offset in reversed(range(7))]
                    date_keys = {day.isoformat(): day.strftime("%a") for day in week}
                    collections = {day.strftime("%a"): 0.0 for day in week}
                    for item in entries:
                        if item["entry_date"] in date_keys:
                            collections[date_keys[item["entry_date"]]] += item["paid"]
                    st.bar_chart(
                        {"Day": list(collections), "Collected": list(collections.values())},
                        x="Day",
                        y="Collected",
                        use_container_width=True,
                        height=260,
                    )
                else:
                    st.info("Your collection trend will appear here after your first order.")
        with activity_column:
            with st.container(border=True):
                st.markdown("### Recent orders")
                st.caption(f"Latest activity · {len(entries):,} orders in your ledger")
                if entries:
                    st.dataframe(
                        [
                            {
                                "Customer": item["customer"],
                                "Date": item["entry_date"],
                                "Order": f"{size_label(item['size_ml'])} × {item['qty']}",
                                "Paid": format_inr(item["paid"]),
                                "Balance": format_inr(item["remaining"]),
                                "Status": status_badge(item["status"]),
                            }
                            for item in entries[:5]
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.info("Your ledger is ready. Add the first customer order to see activity here.")
        st.markdown("### Quick entry")
        st.caption("Add an order and capture any payment received today.")
        add_entry_form(rates)
    elif page == "Customer ledger":
        ledger_view(entries)
    elif page == "New order":
        page_heading(
            "NEW TRANSACTION",
            "Create a customer order",
            "Add an order and capture any payment received today.",
        )
        add_entry_form(rates, expanded=True)
    else:
        settings_view(rates)


def main():
    st.set_page_config(
        page_title="Clearwater · Water business ledger",
        page_icon="💧",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_styles()
    init_db()
    if st.session_state.get("user_id"):
        show_dashboard()
    else:
        show_auth()


if __name__ == "__main__":
    main()
