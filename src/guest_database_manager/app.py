# SPDX-FileCopyrightText: 2024-present Guest Database Manager <admin@example.com>
#
# SPDX-License-Identifier: MIT
"""Streamlit application for Guest Database Manager."""

import io
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Add the parent directory to the Python path to enable imports
sys.path.insert(0, str(Path(__file__).parent))

from database import GuestDatabase
from email_manager import EmailManager, get_common_smtp_configs


def setup_page_config() -> None:
    """Configure the Streamlit page."""
    st.set_page_config(
        page_title="Guest Database Manager", page_icon="👥", layout="wide", initial_sidebar_state="expanded"
    )


def initialize_database() -> GuestDatabase:
    """Initialize the database connection."""
    if "database" not in st.session_state:
        # Use the main database file with the correct schema
        st.session_state.database = GuestDatabase("guest_database.db")
    return st.session_state.database


def initialize_email_manager() -> EmailManager:
    """Initialize the email manager."""
    if "email_manager" not in st.session_state:
        st.session_state.email_manager = EmailManager()
    return st.session_state.email_manager


def display_sidebar_stats(db: GuestDatabase) -> None:
    """Display guest statistics in the sidebar."""
    try:
        stats = db.get_stats()
        email_stats = db.get_email_stats()
        
    except Exception as e:
        st.sidebar.error(f"Error getting stats: {e}")
        return

    with st.sidebar:
        st.header("📊 Guest Statistics")

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Guests", stats["total"])
            st.metric("Processed", stats["processed"])
        with col2:
            st.metric("Unprocessed", stats["unprocessed"])
            if stats["total"] > 0:
                completion_rate = (stats["processed"] / stats["total"]) * 100
                st.metric("Completion", f"{completion_rate:.1f}%")

        # Email statistics
        st.subheader("📧 Guest Actions")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("📧 Total Emails", email_stats.get("total_emails", 0))
            st.metric("✅ Accepted", email_stats.get("accepted_emails", 0))
        with col2:
            st.metric("❌ Rejected", email_stats.get("rejected_emails", 0))
            st.metric("⏭️ Skipped", email_stats.get("skipped_guests", 0))


def display_email_config() -> EmailManager:
    """Display email configuration in sidebar and return configured email manager."""
    email_manager = initialize_email_manager()

    with st.sidebar:
        st.header("📧 Email Configuration")

        # Show info if settings were loaded
        if email_manager.has_saved_config() and email_manager.is_configured():
            st.info("📁 Loaded saved email settings")

        # Email provider selection
        smtp_configs = get_common_smtp_configs()

        # Get saved provider if available
        saved_provider = email_manager.get_saved_provider()
        provider_index = 0
        if saved_provider and saved_provider in smtp_configs:
            provider_index = list(smtp_configs.keys()).index(saved_provider)

        provider = st.selectbox(
            "Email Provider", list(smtp_configs.keys()), index=provider_index, help="Select your email provider"
        )

        config = smtp_configs[provider]

        with st.expander("SMTP Settings", expanded=not email_manager.is_configured()):
            if provider == "Custom":
                smtp_server = st.text_input("SMTP Server", value=config["smtp_server"])
                smtp_port = st.number_input("SMTP Port", value=config["smtp_port"], min_value=1, max_value=65535)
            else:
                smtp_server = config["smtp_server"]
                smtp_port = config["smtp_port"]
                st.info(f"SMTP: {smtp_server}:{smtp_port}")
                st.info(config["note"])

            from_email = st.text_input("From Email", value=email_manager.from_email or "")
            from_name = st.text_input("From Name", value=email_manager.from_name or "Podcast Team")
            username = st.text_input("Username/Email", value=email_manager.username or "")
            password = st.text_input("Password/App Password", type="password")

            # Show helpful hint for Gmail users
            if provider == "Gmail":
                st.info(
                    "💡 **Gmail users**: Use an App Password, not your regular password. Generate one at: Google Account → Security → App passwords"
                )

            if st.button("Save Email Settings"):
                if all([smtp_server, smtp_port, username, password, from_email]):
                    email_manager.configure_smtp(
                        smtp_server=smtp_server,
                        smtp_port=smtp_port,
                        username=username,
                        password=password,
                        from_email=from_email,
                        from_name=from_name,
                    )

                    # Save settings persistently
                    if email_manager.save_config(provider=provider):
                        st.success("✅ Email settings saved and will be remembered!")
                    else:
                        st.success("✅ Email settings configured for this session!")
                        st.warning("⚠️ Could not save settings permanently")
                    st.rerun()
                else:
                    st.error("Please fill in all required fields")

        # Clear saved settings option
        if email_manager.has_saved_config():
            if st.button("🗑️ Clear Saved Settings", help="Remove saved email configuration"):
                if email_manager.clear_saved_config():
                    st.success("✅ Saved settings cleared!")
                    st.rerun()
                else:
                    st.error("❌ Failed to clear saved settings")

        # Email status
        if email_manager.is_configured():
            if email_manager.has_saved_config():
                st.success("✅ Email configured (settings saved)")
            else:
                st.success("✅ Email configured (session only)")
        else:
            st.warning("⚠️ Email not configured")

    return email_manager


def create_stats_chart(stats: dict) -> go.Figure:
    """Create a pie chart for guest statistics."""
    if stats["total"] == 0:
        return None

    fig = go.Figure(
        data=[
            go.Pie(
                labels=["Processed", "Unprocessed"],
                values=[stats["processed"], stats["unprocessed"]],
                hole=0.3,
                marker={"colors": ["#00cc96", "#ffa500"]},
            )
        ]
    )

    fig.update_layout(title="Guest Processing Status", showlegend=True, height=400)

    return fig


def create_email_actions_chart(email_stats: dict) -> go.Figure:
    """Create a pie chart for email actions (accepted, rejected, skipped)."""
    accepted = email_stats.get("accepted_emails", 0)
    rejected = email_stats.get("rejected_emails", 0)
    skipped = email_stats.get("skipped_guests", 0)
    total_actions = accepted + rejected + skipped

    if total_actions == 0:
        return None

    fig = go.Figure(
        data=[
            go.Pie(
                labels=["Accepted", "Rejected", "Skipped"],
                values=[accepted, rejected, skipped],
                hole=0.3,
                marker={"colors": ["#00cc96", "#ff6b6b", "#ffc658"]},
            )
        ]
    )

    fig.update_layout(title="Guest Actions Breakdown", showlegend=True, height=400)

    return fig


def upload_file_section(db: GuestDatabase) -> None:
    """Handle file upload and processing."""
    st.header("📁 Upload Guest Data")

    uploaded_file = st.file_uploader(
        "Choose a CSV or Excel file",
        type=["csv", "xlsx", "xls"],
        help="Upload a CSV or Excel file containing guest data",
    )

    if uploaded_file is not None:
        # Save uploaded file temporarily
        temp_path = Path(f"temp_{uploaded_file.name}")

        try:
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            # Display file info
            st.info(f"📄 File: {uploaded_file.name} ({uploaded_file.size} bytes)")

            # Preview the data
            if st.button("🔍 Preview Data", key="preview_btn"):
                try:
                    if uploaded_file.name.endswith(".csv"):
                        # Try different encodings for preview
                        encodings = ["utf-8", "latin-1", "iso-8859-1", "cp1252"]
                        df = None
                        for encoding in encodings:
                            try:
                                df = pd.read_csv(io.StringIO(uploaded_file.getvalue().decode(encoding)))
                                break
                            except UnicodeDecodeError:
                                continue
                    else:
                        df = pd.read_excel(uploaded_file)

                    if df is not None:
                        st.subheader("📋 Data Preview")
                        st.dataframe(df.head(10), use_container_width=True)
                        st.info(f"Total rows: {len(df)}")
                    else:
                        st.error("Unable to read the file. Please check the encoding.")

                except Exception as e:
                    st.error(f"Error previewing file: {e!s}")

            # Process the file
            if st.button("✅ Process File", key="process_btn", type="primary"):
                with st.spinner("Processing file..."):
                    if temp_path.suffix.lower() == '.csv':
                        result = db.import_from_csv(str(temp_path))
                    else:
                        result = db.import_from_excel(str(temp_path))

                    if result["imported"] or result["updated"]:
                        st.success("🎉 File processed successfully!")

                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("New Guests", result["imported"])
                        with col2:
                            st.metric("Updated Guests", result["updated"])
                        with col3:
                            st.metric("Skipped Rows", result["skipped"])
                        with col4:
                            st.metric("Errors", result["errors"])

                        # Force refresh of the app
                        st.rerun()
                    else:
                        if result["errors"] > 0:
                            st.error(f"❌ Error processing file: {result['errors']} errors occurred")
                        else:
                            st.warning("⚠️ No new data was imported")

        finally:
            # Clean up temporary file
            if temp_path.exists():
                temp_path.unlink()


def display_guest_table(db: GuestDatabase, email_manager: EmailManager) -> None:
    """Display and manage the guest table."""
    st.header("👥 Guest Management")

    # Get all guests
    guests_list = db.get_all_guests()

    if not guests_list:
        st.info("📝 No guests found. Upload a file to get started!")
        return

    # Convert to DataFrame for easier manipulation
    guests_df = pd.DataFrame(guests_list)

    # Filter options
    col1, col2, col3 = st.columns(3)

    with col1:
        status_filter = st.selectbox("Filter by Status", ["All", "Processed", "Unprocessed"], key="status_filter")

    with col2:
        search_term = st.text_input("Search by Name/Email", key="search_term")

    with col3:
        items_per_page = st.selectbox("Items per Page", [10, 25, 50, 100], index=1, key="items_per_page")

    # Apply filters
    filtered_df = guests_df.copy()

    if status_filter == "Processed":
        filtered_df = filtered_df[filtered_df["is_processed"] == 1]
    elif status_filter == "Unprocessed":
        filtered_df = filtered_df[filtered_df["is_processed"] == 0]

    if search_term:
        mask = (
            filtered_df["full_name"].str.contains(search_term, case=False, na=False)
            | filtered_df["email"].str.contains(search_term, case=False, na=False)
        )
        # Add more searchable fields if they exist
        if "current_path" in filtered_df.columns:
            mask = mask | filtered_df["current_path"].str.contains(search_term, case=False, na=False)
        if "personal_professional_background" in filtered_df.columns:
            mask = mask | filtered_df["personal_professional_background"].str.contains(search_term, case=False, na=False)
        filtered_df = filtered_df[mask]

    # Pagination
    total_items = len(filtered_df)
    total_pages = (total_items - 1) // items_per_page + 1 if total_items > 0 else 1

    if total_pages > 1:
        page = st.selectbox(f"Page (1-{total_pages})", range(1, total_pages + 1), key="page_selector")
        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        display_df = filtered_df.iloc[start_idx:end_idx]
    else:
        display_df = filtered_df

    st.info(f"Showing {len(display_df)} of {total_items} guests")

    # Display table with actions
    for idx, row in display_df.iterrows():
        with st.container():
            col1, col2, col3, col4 = st.columns([3, 2, 1, 1])

            with col1:
                st.write(f"**{row['full_name']}**")
                # Handle email display properly for NULL/empty values
                email = row.get('email')
                if email and pd.notna(email) and email.strip():
                    st.write(f"📧 {email}")
                else:
                    st.write("📧 No email address")
                # Display website if available
                if pd.notna(row.get("website")) and row["website"]:
                    website_url = row["website"].strip()
                    if website_url and not website_url.lower().startswith("http"):
                        website_url = "https://" + website_url
                    st.write(f"🌐 [Website]({website_url})")
                
                # Display social media if available
                if pd.notna(row.get("social_media_handles")) and row["social_media_handles"]:
                    st.write(f"📱 Social: {row['social_media_handles']}")

            with col2:
                status_color = "🟢" if row["is_processed"] else "🔴"
                status_text = "Processed" if row["is_processed"] else "Unprocessed"
                st.write(f"{status_color} {status_text}")

                # Use date_added for when the guest was added
                if pd.notna(row.get("date_added")) and row["date_added"]:
                    st.write(f"📅 Added: {str(row['date_added'])[:10]}")

                # Show email status if available
                if pd.notna(row.get("email_status")) and row["email_status"]:
                    st.write(f"� Email: {row['email_status']}")

                # Show following status if available
                if pd.notna(row.get("following_us")) and row["following_us"]:
                    following_status = "✅" if str(row["following_us"]).lower() in ["yes", "true", "1"] else "❌"
                    st.write(f"👥 Following: {following_status}")

            with col3:
                if row["is_processed"]:
                    # Show current email status
                    email_status = row.get("email_status", "")
                    if email_status == "accepted":
                        st.success("✅ Accepted")
                    elif email_status == "rejected":
                        st.error("❌ Rejected")
                    elif email_status == "skipped":
                        st.warning("⏭️ Skipped")
                    else:
                        st.info("📝 Processed")

                    if st.button("Mark Unprocessed", key=f"unprocess_{row['id']}"):
                        db.mark_guest_unprocessed(row["id"])
                        st.rerun()
                else:
                    # Show Accept/Reject/Skip buttons for unprocessed guests
                    col3a, col3b, col3c = st.columns(3)

                    with col3a:
                        if st.button("✅ Accept", key=f"accept_{row['id']}", type="primary"):
                            st.session_state[f"show_accept_dialog_{row['id']}"] = True
                            st.rerun()

                    with col3b:
                        if st.button("❌ Reject", key=f"reject_{row['id']}"):
                            st.session_state[f"show_reject_dialog_{row['id']}"] = True
                            st.rerun()

                    with col3c:
                        if st.button("⏭️ Skip", key=f"skip_{row['id']}"):
                            st.session_state[f"show_skip_dialog_{row['id']}"] = True
                            st.rerun()

            with col4:
                if st.button("🗑️ Delete", key=f"delete_{row['id']}"):
                    if st.session_state.get(f"confirm_delete_{row['id']}", False):
                        db.delete_guest(row["id"])
                        st.rerun()
                    else:
                        st.session_state[f"confirm_delete_{row['id']}"] = True
                        st.warning("Click again to confirm deletion")

            # Expandable details section
            with st.expander(f"View Details - {row['full_name']}", expanded=False):
                col1, col2 = st.columns(2)

                with col1:
                    st.subheader("📋 Basic Information")
                    if pd.notna(row.get("personal_professional_background")) and row["personal_professional_background"]:
                        st.write("**Background:**")
                        st.write(row["personal_professional_background"])

                    if pd.notna(row.get("motivation")) and row["motivation"]:
                        st.write("**Motivation:**")
                        st.write(row["motivation"])

                    if pd.notna(row.get("core_values")) and row["core_values"]:
                        st.write("**Core Values:**")
                        st.write(row["core_values"])

                    if pd.notna(row.get("favourite_quote")) and row["favourite_quote"]:
                        st.write("**Favorite Quote:**")
                        st.write(row["favourite_quote"])

                with col2:
                    st.subheader("🎙️ Podcast Relevant")
                    if pd.notna(row.get("passionate_topics")) and row["passionate_topics"]:
                        st.write("**Passionate Topics:**")
                        st.write(row["passionate_topics"])

                    if pd.notna(row.get("message_takeaway")) and row["message_takeaway"]:
                        st.write("**Message/Takeaway:**")
                        st.write(row["message_takeaway"])

                    if pd.notna(row.get("podcast_experience")) and row["podcast_experience"]:
                        st.write("**Podcast Experience:**")
                        st.write(row["podcast_experience"])

                    if pd.notna(row.get("additional_info")) and row["additional_info"]:
                        st.write("**Additional Info:**")
                        st.write(row["additional_info"])

                # Social media and following status
                st.subheader("🌐 Online Presence")
                col3, col4 = st.columns(2)

                with col3:
                    if pd.notna(row.get("social_media")) and row["social_media"]:
                        st.write("**Social Media Handles:**")
                        st.write(row["social_media"])

                with col4:
                    if pd.notna(row.get("following_status")) and row["following_status"]:
                        st.write("**Following Status:**")
                        st.write(row["following_status"])

            # Email action dialogs
            handle_email_dialogs(row, db, email_manager)

            st.divider()


def handle_email_dialogs(row: dict, db: GuestDatabase, email_manager: EmailManager) -> None:
    """Handle accept/reject email dialogs for a guest."""
    guest_id = row["id"]
    guest_name = row["full_name"]
    guest_email = row.get("email")

    # Accept dialog
    if st.session_state.get(f"show_accept_dialog_{guest_id}", False):
        with st.container():
            st.subheader(f"✅ Accept Guest: {guest_name}")

            if not guest_email:
                st.error("⚠️ No email address found for this guest!")
                if st.button("Close", key=f"close_accept_no_email_{guest_id}"):
                    st.session_state[f"show_accept_dialog_{guest_id}"] = False
                    st.rerun()
                return

            st.info(f"📧 Email will be sent to: {guest_email}")

            # Custom message option
            custom_message = st.text_area(
                "Custom Message (optional)",
                placeholder="Add a personalized message to the acceptance email...",
                key=f"accept_message_{guest_id}",
                help="This message will be included at the beginning of the email",
            )

            # Preview email
            if st.checkbox("Preview Email", key=f"preview_accept_{guest_id}"):
                template = email_manager.get_acceptance_template(guest_name, custom_message)
                st.text_area("Email Subject", value=template["subject"], disabled=True)
                st.text_area("Email Body", value=template["body"], height=200, disabled=True)

            # Action buttons
            col1, col2, col3 = st.columns(3)

            with col1:
                if st.button("✅ Send & Accept", key=f"confirm_accept_{guest_id}", type="primary"):
                    if email_manager.is_configured():
                        if email_manager.send_acceptance_email(guest_name, guest_email, custom_message):
                            db.accept_guest_with_email(guest_id, custom_message)
                            st.success(f"✅ Acceptance email sent to {guest_name}!")
                            st.session_state[f"show_accept_dialog_{guest_id}"] = False
                            st.rerun()
                        else:
                            st.error("❌ Failed to send email. Please check your email configuration.")
                    else:
                        st.error("❌ Email not configured. Please configure email settings in the sidebar.")

            with col2:
                if st.button("📝 Accept Without Email", key=f"accept_no_email_{guest_id}"):
                    db.mark_guest_processed(guest_id)
                    st.success(f"✅ {guest_name} marked as accepted (no email sent)")
                    st.session_state[f"show_accept_dialog_{guest_id}"] = False
                    st.rerun()

            with col3:
                if st.button("❌ Cancel", key=f"cancel_accept_{guest_id}"):
                    st.session_state[f"show_accept_dialog_{guest_id}"] = False
                    st.rerun()

    # Reject dialog
    if st.session_state.get(f"show_reject_dialog_{guest_id}", False):
        with st.container():
            st.subheader(f"❌ Reject Guest: {guest_name}")

            if not guest_email:
                st.error("⚠️ No email address found for this guest!")
                if st.button("Close", key=f"close_reject_no_email_{guest_id}"):
                    st.session_state[f"show_reject_dialog_{guest_id}"] = False
                    st.rerun()
                return

            st.info(f"📧 Email will be sent to: {guest_email}")

            # Custom message option
            custom_message = st.text_area(
                "Custom Message (optional)",
                placeholder="Add a personalized message to the rejection email...",
                key=f"reject_message_{guest_id}",
                help="This message will be included at the beginning of the email",
            )

            # Preview email
            if st.checkbox("Preview Email", key=f"preview_reject_{guest_id}"):
                template = email_manager.get_rejection_template(guest_name, custom_message)
                st.text_area("Email Subject", value=template["subject"], disabled=True)
                st.text_area("Email Body", value=template["body"], height=200, disabled=True)

            # Action buttons
            col1, col2, col3 = st.columns(3)

            with col1:
                if st.button("❌ Send & Reject", key=f"confirm_reject_{guest_id}", type="primary"):
                    if email_manager.is_configured():
                        if email_manager.send_rejection_email(guest_name, guest_email, custom_message):
                            db.reject_guest_with_email(guest_id, custom_message)
                            st.success(f"📧 Rejection email sent to {guest_name}")
                            st.session_state[f"show_reject_dialog_{guest_id}"] = False
                            st.rerun()
                        else:
                            st.error("❌ Failed to send email. Please check your email configuration.")
                    else:
                        st.error("❌ Email not configured. Please configure email settings in the sidebar.")

            with col2:
                if st.button("📝 Reject Without Email", key=f"reject_no_email_{guest_id}"):
                    db.mark_guest_processed(guest_id)
                    st.success(f"❌ {guest_name} marked as rejected (no email sent)")
                    st.session_state[f"show_reject_dialog_{guest_id}"] = False
                    st.rerun()

            with col3:
                if st.button("❌ Cancel", key=f"cancel_reject_{guest_id}"):
                    st.session_state[f"show_reject_dialog_{guest_id}"] = False
                    st.rerun()

    # Skip dialog
    if st.session_state.get(f"show_skip_dialog_{guest_id}", False):
        with st.container():
            st.subheader(f"⏭️ Skip Guest: {guest_name}")
            st.info("This guest will be marked as processed without sending any email.")

            # Optional reason for skipping
            skip_reason = st.text_area(
                "Reason for Skipping (optional)",
                placeholder="Enter why you're skipping this guest (for your records)...",
                key=f"skip_reason_{guest_id}",
                help="This reason will be stored for your reference but not sent to the guest",
            )

            # Warning message
            st.warning("⚠️ The guest will NOT receive any notification about their application status.")

            # Action buttons
            col1, col2 = st.columns(2)

            with col1:
                if st.button("⏭️ Confirm Skip", key=f"confirm_skip_{guest_id}", type="primary"):
                    db.skip_guest(guest_id, skip_reason)
                    st.success(f"⏭️ {guest_name} marked as skipped (no email sent)")
                    st.session_state[f"show_skip_dialog_{guest_id}"] = False
                    st.rerun()

            with col2:
                if st.button("❌ Cancel", key=f"cancel_skip_{guest_id}"):
                    st.session_state[f"show_skip_dialog_{guest_id}"] = False
                    st.rerun()


def display_analytics(db: GuestDatabase) -> None:
    """Display analytics and visualizations."""
    st.header("📈 Analytics")

    guests_list = db.get_all_guests()

    if not guests_list:
        st.info("📊 No data available for analytics. Upload guest data first!")
        return

    # Convert to DataFrame for analysis
    guests_df = pd.DataFrame(guests_list)

    # Stats overview
    stats = db.get_stats()
    email_stats = db.get_email_stats()

    col1, col2 = st.columns(2)

    with col1:
        # Processing status pie chart
        chart = create_stats_chart(stats)
        if chart:
            st.plotly_chart(chart, use_container_width=True)

    with col2:
        # Email actions pie chart
        email_chart = create_email_actions_chart(email_stats)
        if email_chart:
            st.plotly_chart(email_chart, use_container_width=True)
        else:
            st.info("📧 No email actions yet. Start accepting, rejecting, or skipping guests to see the breakdown.")

    # Second row of charts
    col3, col4 = st.columns(2)

    with col3:
        # Guests added over time
        if "date_added" in guests_df.columns:
            try:
                # Handle mixed datetime formats with flexible parsing
                guests_df["date_added"] = pd.to_datetime(guests_df["date_added"], format='mixed', errors='coerce')
                
                # Remove any rows where date parsing failed
                valid_dates = guests_df["date_added"].notna()
                
                if valid_dates.sum() > 0:
                    # Create a timeline chart
                    timeline_df = guests_df[valid_dates].copy()
                    timeline_df["date_only"] = timeline_df["date_added"].dt.date
                    daily_counts = timeline_df.groupby("date_only").size().reset_index(name="count")
                    
                    if len(daily_counts) > 1:
                        fig = px.line(
                            daily_counts,
                            x="date_only",
                            y="count",
                            title="Guests Added Over Time",
                            labels={"date_only": "Date", "count": "Number of Guests"}
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("📅 Need more data points to show timeline")
                else:
                    st.info("📅 No valid dates found for timeline")
            except Exception as e:
                st.warning(f"⚠️ Could not parse dates for timeline: {e}")
                st.info("📅 Timeline unavailable due to date format issues")

    with col4:
        # Email actions summary table
        accepted = email_stats.get("accepted_emails", 0)
        rejected = email_stats.get("rejected_emails", 0)
        skipped = email_stats.get("skipped_guests", 0)
        total_emails = email_stats.get("total_emails", 0)
        
        if accepted + rejected + skipped > 0:
            st.subheader("📊 Email Actions Summary")
            summary_data = {
                "Action": ["Accepted", "Rejected", "Skipped"],
                "Count": [accepted, rejected, skipped],
                "Percentage": [
                    f"{(accepted/(accepted+rejected+skipped)*100):.1f}%" if (accepted+rejected+skipped) > 0 else "0%",
                    f"{(rejected/(accepted+rejected+skipped)*100):.1f}%" if (accepted+rejected+skipped) > 0 else "0%",
                    f"{(skipped/(accepted+rejected+skipped)*100):.1f}%" if (accepted+rejected+skipped) > 0 else "0%"
                ]
            }
            summary_df = pd.DataFrame(summary_data)
            st.dataframe(summary_df, use_container_width=True)
        else:
            st.info("📊 No email actions to summarize yet")

    # Additional insights
    st.subheader("📋 Data Insights")

    col1, col2 = st.columns(2)

    with col1:
        # Most common professions
        if "profession" in guests_df.columns:
            profession_counts = guests_df["profession"].dropna().astype(str)
            profession_counts = profession_counts[profession_counts.str.strip() != ""]
            top_professions = profession_counts.value_counts().head(10)
            if not top_professions.empty:
                fig = px.bar(
                    x=top_professions.values,
                    y=top_professions.index,
                    orientation="h",
                    title="Top Professions",
                    labels={"x": "Count", "y": "Profession"},
                )
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No profession data available.")

    with col2:
        # Source files
        if "original_file_name" in guests_df.columns:
            file_counts = guests_df["original_file_name"].dropna().astype(str)
            file_counts = file_counts[file_counts.str.strip() != ""]
            source_files = file_counts.value_counts()
            if not source_files.empty:
                fig = px.pie(values=source_files.values, names=source_files.index, title="Guests by Source File")
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No source file data available.")


def main() -> None:
    """Main Streamlit application."""
    setup_page_config()

    st.title("👥 Guest Database Manager")
    st.markdown("Manage guest data from CSV/Excel files with database persistence and visualization.")

    # Initialize database and email manager
    db = initialize_database()
    email_manager = display_email_config()

    # Display sidebar stats
    display_sidebar_stats(db)

    # Main content tabs
    tab1, tab2, tab3 = st.tabs(["📁 Upload", "👥 Manage Guests", "📈 Analytics"])

    with tab1:
        upload_file_section(db)

    with tab2:
        display_guest_table(db, email_manager)

    with tab3:
        display_analytics(db)

    # Footer
    st.markdown("---")
    st.markdown("Built with ❤️ for MIRROR TALK Podcast")


if __name__ == "__main__":
    main()
