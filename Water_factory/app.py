from contextlib import closing
from datetime import date, timedelta
import csv
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
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
        :root {
            --ink:#142f38; --muted:#71858a; --teal:#087e80; --deep:#075e67;
            --line:#e5edeb; --paper:#ffffff; --mint:#dff5ed;
        }
        html, body, [class*="css"] { font-family:'DM Sans',sans-serif; }
        .stApp {
            background:
                radial-gradient(ellipse at 80% 5%,rgba(203,239,229,.36),transparent 28%),
                linear-gradient(145deg,#f5f8f7 0%,#f5f8fa 56%,#eff7f5 100%);
            color:var(--ink);
        }
        [data-testid="stHeader"] { background:transparent; }
        [data-testid="stSidebar"] { background:#102f37; border-right:0; }
        [data-testid="stSidebar"] * { color:#e9f4f2; }
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color:#a9c2c1; }
        [data-testid="stSidebar"] [data-testid="stRadio"] label { border-radius:10px; }
        .block-container { max-width:1320px; padding:2rem 2rem 3rem; }
        h1,h2,h3 { font-family:'Manrope',sans-serif !important; letter-spacing:-.04em; color:var(--ink); }
        h1 { font-size:2.1rem !important; font-weight:800 !important; }
        h2 { font-size:1.35rem !important; font-weight:700 !important; }
        h3 { font-weight:700 !important; }
        [data-testid="stMetric"] {
            background:var(--paper); border:1px solid var(--line); border-radius:18px;
            padding:1.15rem 1.3rem; box-shadow:0 8px 30px rgba(27,64,67,.045);
        }
        [data-testid="stMetricLabel"] p { color:var(--muted) !important; font-weight:600; }
        [data-testid="stMetricValue"] { color:var(--ink); font-family:'Manrope',sans-serif; font-weight:800; }
        div[data-testid="stForm"], div[data-testid="stExpander"] {
            background:var(--paper); border:1px solid var(--line); border-radius:16px;
        }
        div[data-testid="stForm"] { padding:1.2rem; }
        .stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {
            border-radius:10px; border:0; background:var(--teal); color:white;
            font-weight:700; padding:.62rem 1rem; transition:all .18s ease;
        }
        .stButton > button:hover, .stFormSubmitButton > button:hover, .stDownloadButton > button:hover {
            background:var(--deep); color:white; transform:translateY(-1px);
        }
        .stTextInput input, .stNumberInput input, .stDateInput input,
        [data-baseweb="select"] > div { border-radius:10px !important; }
        [data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:14px; overflow:hidden; }
        .hero {
            position:relative; overflow:hidden; background:linear-gradient(118deg,#103c47 0%,#087e80 60%,#37a994 100%);
            padding:2.25rem 2.5rem; border-radius:22px; color:#fff; margin:0 0 1.4rem;
            box-shadow:0 18px 40px rgba(8,111,115,.16);
        }
        .hero:after {
            content:""; position:absolute; width:260px; height:260px; right:5%; top:-150px;
            border:1px solid rgba(255,255,255,.18); border-radius:50%;
            box-shadow:0 0 0 28px rgba(255,255,255,.035),0 0 0 58px rgba(255,255,255,.025);
        }
        .hero h2 { color:#fff !important; font-size:1.8rem !important; margin:0 0 .4rem; }
        .hero p { color:#d6f1eb; margin:0; }
        .eyebrow { color:#91dfcd !important; text-transform:uppercase; font-size:.7rem; letter-spacing:.16em; font-weight:700; margin-bottom:.65rem !important; }
        .section-kicker { color:var(--teal); text-transform:uppercase; letter-spacing:.13em; font-size:.7rem; font-weight:700; }
        .stCaption { color:var(--muted); }
        .auth-showcase {
            position:relative; overflow:hidden; min-height:570px; height:100%;
            padding:2.3rem; border-radius:26px; color:#fff;
            background:linear-gradient(150deg,#103840 0%,#0b6268 56%,#158f88 100%);
            box-shadow:0 22px 55px rgba(13,71,75,.16);
            display:flex; flex-direction:column; justify-content:space-between;
        }
        .auth-showcase:before,.auth-showcase:after {
            content:""; position:absolute; border:1px solid rgba(220,255,245,.13); border-radius:50%;
            pointer-events:none;
        }
        .auth-showcase:before { width:330px;height:330px;right:-150px;top:90px;box-shadow:0 0 0 25px rgba(220,255,245,.035),0 0 0 55px rgba(220,255,245,.025); }
        .auth-showcase:after { width:180px;height:180px;left:-105px;bottom:-80px; }
        .auth-brand,.auth-copy,.auth-footnote { position:relative; z-index:1; }
        .auth-brand { display:flex; align-items:center; gap:.7rem; font:800 1.15rem Manrope,sans-serif; letter-spacing:-.04em; }
        .brand-mark {
            width:38px;height:38px;display:inline-flex;align-items:center;justify-content:center;
            background:rgba(218,250,239,.14);border:1px solid rgba(218,250,239,.2);
            color:#c4f4e3;border-radius:12px;font-size:1.2rem;
        }
        .auth-copy { margin:auto 0; padding:2.3rem 0; max-width:440px; }
        .auth-copy .eyebrow { color:#9ce6d2 !important; }
        .auth-copy h2 { color:#fff !important; font-size:2.5rem !important; line-height:1.12; margin:.4rem 0 1rem; }
        .auth-copy p { color:#d0e9e5; line-height:1.7; font-size:1rem; }
        .auth-points { display:grid; gap:.85rem; margin-top:1.8rem; }
        .auth-point { display:flex; align-items:center; gap:.7rem; color:#e4f5f0; font-size:.9rem; }
        .auth-point span { color:#a6ead5; font-weight:700; }
        .auth-footnote { color:#a8cfca; font-size:.78rem; }
        .auth-form-title { margin:.8rem 0 .35rem !important; }
        .auth-form-caption { margin:0 0 1.35rem; color:var(--muted); }
        @media (max-width:850px) {
            .block-container{padding:1.2rem 1rem 2rem;}
            .auth-showcase{min-height:330px;padding:1.6rem;}
            .auth-copy{padding:2rem 0 1rem;}
            .auth-copy h2{font-size:2rem !important;}
        }
        @media (max-width:600px) {
            .hero{padding:1.55rem;}
            .auth-showcase{min-height:300px;border-radius:20px;}
            h1{font-size:1.8rem !important;}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def show_auth():
    first_account = not account_exists()
    if "auth_mode" not in st.session_state:
        st.session_state.auth_mode = "signup" if first_account else "login"
    if not first_account:
        st.session_state.auth_mode = "login"
    mode = st.session_state.auth_mode
    title = "Your ledger, beautifully in balance." if mode == "signup" else "Welcome back."
    caption = (
        "Create your owner account and bring every order, payment and balance into focus."
        if mode == "signup"
        else "Sign in to pick up where your business left off. Your records are waiting."
    )
    st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)
    showcase, form_column = st.columns([1.04, 0.96], gap="large")
    with showcase:
        st.markdown(
            """<section class="auth-showcase">
            <div class="auth-brand"><span class="brand-mark">◉</span> Clearwater</div>
            <div class="auth-copy">
                <p class="eyebrow">A clearer way to run your business</p>
                <h2>Every drop.<br>Every detail.</h2>
                <p>A calm, dependable workspace for your water business — from the first order to the final payment.</p>
                <div class="auth-points">
                    <div class="auth-point"><span>✓</span> Keep customer orders in one place</div>
                    <div class="auth-point"><span>✓</span> See payments and balances at a glance</div>
                    <div class="auth-point"><span>✓</span> Stay in control of your bottle rates</div>
                </div>
            </div>
            <div class="auth-footnote">PRIVATE BY DESIGN&nbsp; · &nbsp;BUILT FOR YOUR BUSINESS</div>
            </section>""",
            unsafe_allow_html=True,
        )
    with form_column:
        st.markdown(
            f"""<p class="section-kicker">{'OWNER ACCOUNT SETUP' if mode == 'signup' else 'OWNER SIGN IN'}</p>
            <h1 class="auth-form-title">{title}</h1>
            <p class="auth-form-caption">{caption}</p>""",
            unsafe_allow_html=True,
        )
        if mode == "signup":
            with st.form("signup_form"):
                username = st.text_input("Username", placeholder="Choose a username", autocomplete="username")
                password = st.text_input("Password", type="password", placeholder="At least 8 characters", autocomplete="new-password", max_chars=72)
                confirm_password = st.text_input("Confirm password", type="password", placeholder="Enter your password again", autocomplete="new-password")
                submitted = st.form_submit_button("Create your account", use_container_width=True)
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
                    try:
                        with closing(connect_db()) as connection, connection:
                            if connection.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                                st.error("An owner account already exists. Please sign in.")
                            else:
                                cursor = connection.execute(
                                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                                    (username, password_hash(password)),
                                )
                                st.session_state.user_id = cursor.lastrowid
                                st.session_state.username = username
                                st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("That username is already in use. Please choose another.")
        else:
            with st.form("login_form"):
                username = st.text_input("Username", placeholder="Your username", autocomplete="username")
                password = st.text_input("Password", type="password", placeholder="Your password", autocomplete="current-password")
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


def add_entry_form(rates):
    with st.expander("＋  Add a customer entry", expanded=False):
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


def ledger_view(entries):
    st.subheader("Customer ledger")
    st.caption("Track every order, payment and outstanding balance in one place.")
    add_entry_form(fetch_dashboard()[1])
    controls = st.columns([1, 2, 1])
    with controls[0]:
        status_filter = st.selectbox("Payment status", ["All", "Due", "Partial", "Paid"])
    with controls[1]:
        search = st.text_input("Search customers", placeholder="Search by customer name")
    filtered = [
        entry for entry in entries
        if (status_filter == "All" or entry["status"] == status_filter)
        and search.casefold() in entry["customer"].casefold()
    ]
    st.caption(f"{len(filtered)} {'entry' if len(filtered) == 1 else 'entries'}")
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
    st.subheader("Business settings")
    st.caption("Manage your bottle pricing and reset your ledger when you need a fresh start.")
    st.markdown("#### Bottle rates")
    st.caption("Updated rates apply to new entries. Existing orders keep their original price.")
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
    st.divider()
    st.markdown("#### Reset ledger")
    st.caption("This permanently removes all customer entries and restores default bottle rates. Your login remains unchanged.")
    if not st.session_state.get("confirm_reset"):
        if st.button("Reset all ledger data"):
            st.session_state.confirm_reset = True
            st.rerun()
    else:
        st.warning("This action cannot be undone. Are you sure you want to clear the ledger?")
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
    with st.sidebar:
        st.markdown(
            '<div style="font:800 1.25rem Manrope,sans-serif;color:#fff;padding:.5rem 0 1.1rem">◉ Clearwater</div>',
            unsafe_allow_html=True,
        )
        st.caption("WATER BUSINESS · FINANCE")
        page = st.radio("Workspace", ["Overview", "Customer ledger", "Settings"], label_visibility="collapsed")
        st.divider()
        st.markdown(f"**{st.session_state.username}**")
        st.caption("Owner account")
        if st.button("Sign out", use_container_width=True):
            for key in ("user_id", "username", "confirm_reset", "confirm_delete_id"):
                st.session_state.pop(key, None)
            st.rerun()

    entries, rates, collected, outstanding, customer_count = fetch_dashboard()
    if page == "Overview":
        st.markdown(
            f"""<div class="hero"><p class="eyebrow">Business at a glance</p>
            <h2>Good business starts with a clear view.</h2>
            <p>Your water sales, payments and customer balances — all in one calm workspace.</p></div>""",
            unsafe_allow_html=True,
        )
        first, second, third = st.columns(3)
        first.metric("Total collected", format_inr(collected), help="Payments received across all entries")
        second.metric("Outstanding balance", format_inr(outstanding), help="Amount still owed by customers")
        third.metric("Customers on ledger", f"{customer_count:,}", help="Unique customer names")
        st.write("")
        chart_column, activity_column = st.columns(2, gap="large")
        with chart_column:
            st.subheader("Collections")
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
            st.subheader("Recent activity")
            st.caption(f"The latest orders added to your ledger · {len(entries):,} total")
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
                st.info("Your ledger is ready. Add the first customer entry to see activity here.")
        add_entry_form(rates)
    elif page == "Customer ledger":
        ledger_view(entries)
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
