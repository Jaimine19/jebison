import csv
import io
from datetime import date, timedelta

import streamlit as st

import app as ledger


def show_overview(entries, collected, outstanding, customer_count):
    st.markdown(
        f"""<div class="hero"><div>
        <p class="eyebrow">CLEARWATER · PUBLIC DASHBOARD</p>
        <h2>A clearer view of the water business.</h2>
        <p>Sales, collections and customer balances in one place.</p>
        </div><div class="hero-note">UPDATED<strong>{date.today().strftime('%d %b %Y')}</strong></div></div>""",
        unsafe_allow_html=True,
    )
    first, second = st.columns(2)
    first.metric("Total collected", ledger.format_inr(collected))
    second.metric("Outstanding balance", ledger.format_inr(outstanding))
    third, fourth = st.columns(2)
    third.metric("Customers", f"{customer_count:,}")
    fourth.metric("Total orders", f"{len(entries):,}")

    chart_column, activity_column = st.columns(2, gap="large")
    with chart_column:
        with st.container(border=True):
            st.markdown("### Weekly collections")
            st.caption("Payments received over the last seven days")
            if entries:
                week = [date.today() - timedelta(days=offset) for offset in reversed(range(7))]
                date_labels = {day.isoformat(): day.strftime("%a") for day in week}
                collections = {day.strftime("%a"): 0.0 for day in week}
                for entry in entries:
                    if entry["entry_date"] in date_labels:
                        collections[date_labels[entry["entry_date"]]] += entry["paid"]
                st.bar_chart(
                    {"Day": list(collections), "Collected": list(collections.values())},
                    x="Day",
                    y="Collected",
                    height=260,
                )
            else:
                st.info("Collection activity will appear here when data is available.")

    with activity_column:
        with st.container(border=True):
            st.markdown("### Recent orders")
            st.caption(f"Latest activity · {len(entries):,} orders in the ledger")
            if entries:
                st.dataframe(
                    [
                        {
                            "Customer": entry["customer"],
                            "Date": entry["entry_date"],
                            "Order": f"{ledger.size_label(entry['size_ml'])} × {entry['qty']}",
                            "Paid": ledger.format_inr(entry["paid"]),
                            "Balance": ledger.format_inr(entry["remaining"]),
                            "Status": ledger.status_badge(entry["status"]),
                        }
                        for entry in entries[:5]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("Recent orders will appear here when data is available.")


def show_ledger(entries):
    ledger.page_heading(
        "CUSTOMER RECORDS",
        "Customer ledger",
        "Browse orders and payment balances. This view is read-only.",
    )
    controls = st.columns([1, 2])
    with controls[0]:
        status_filter = st.selectbox(
            "Payment status",
            ["All", "Outstanding", "Due", "Partial", "Paid"],
            key="public_ledger_status",
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
    if not filtered:
        st.info("No customer entries match these filters.")
        return

    table_rows = [
        {
            "Customer": entry["customer"],
            "Date": entry["entry_date"],
            "Product": f"{ledger.size_label(entry['size_ml'])} × {entry['qty']}",
            "Total": ledger.format_inr(entry["total"]),
            "Paid": ledger.format_inr(entry["paid"]),
            "Balance": ledger.format_inr(entry["remaining"]),
            "Status": ledger.status_badge(entry["status"]),
        }
        for entry in filtered
    ]
    with st.container(border=True):
        st.dataframe(table_rows, use_container_width=True, hide_index=True)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=table_rows[0].keys())
    writer.writeheader()
    writer.writerows(table_rows)
    st.download_button(
        "Download this ledger as CSV",
        output.getvalue(),
        "water-factory-ledger.csv",
        "text/csv",
    )


def main():
    st.set_page_config(
        page_title="Clearwater · Public dashboard",
        page_icon="💧",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    ledger.inject_styles()
    ledger.init_db()
    entries, _, collected, outstanding, customer_count = ledger.fetch_dashboard()

    st.markdown(
        '<div class="brand-lockup"><span class="brand-symbol">◉</span> Clearwater'
        '<span class="section-kicker">&nbsp; · &nbsp; PUBLIC VIEW</span></div>',
        unsafe_allow_html=True,
    )
    overview_tab, ledger_tab = st.tabs(["Overview", "Customer ledger"])
    with overview_tab:
        show_overview(entries, collected, outstanding, customer_count)
    with ledger_tab:
        show_ledger(entries)


if __name__ == "__main__":
    main()
